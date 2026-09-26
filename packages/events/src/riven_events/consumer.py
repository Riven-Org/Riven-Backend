"""Idempotent stream consumer (S01.3.2).

Each consumer is a Redis consumer group. For every message the handler runs in a database
transaction that also inserts (consumer, event_id) into `processed_events`; if that row
already exists the event was handled before and the handler is skipped. The message is
acknowledged only after the transaction commits, so a crash means redelivery (at-least-once)
and never a second side effect.
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ResponseError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_events.models import ProcessedEvent
from riven_events.relay import STREAM
from riven_schemas import DomainEvent
from riven_schemas.contracts import parse_event

Message = tuple[str, dict[str, str]]
Handler = Callable[[AsyncSession, DomainEvent], Awaitable[None]]
log = logging.getLogger(__name__)


class EventConsumer:
    def __init__(
        self,
        name: str,
        sessions: async_sessionmaker[AsyncSession],
        redis: "Redis",
        handlers: Mapping[str, Handler],
        *,
        stream: str = STREAM,
        worker_id: str = "worker-1",
        reclaim_idle_ms: int = 60_000,
    ) -> None:
        self.name = name
        self._sessions = sessions
        self._redis = redis
        self._handlers = dict(handlers)
        self._stream = stream
        self._worker_id = worker_id
        self._reclaim_idle_ms = reclaim_idle_ms

    async def ensure_group(self) -> None:
        try:
            await self._redis.xgroup_create(self._stream, self.name, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def process_once(self, *, count: int = 50, block_ms: int | None = None) -> int:
        """Handle messages this worker left unacknowledged, then new ones. Returns count."""
        await self.ensure_group()
        messages = await self._reclaim(count)
        # RESP2 reply shape (the redis-py default): [(stream, [(id, fields), ...])]
        response = cast(
            list[tuple[str, list[Message]]],
            await self._redis.xreadgroup(
                self.name, self._worker_id, {self._stream: ">"}, count=count, block=block_ms
            ),
        )
        for _stream, entries in response or []:
            messages.extend(entries)
        for message_id, fields in messages:
            await self._handle(message_id, fields)
        return len(messages)

    async def _reclaim(self, count: int) -> list[Message]:
        """Take over messages another (crashed) worker read but never acknowledged."""
        result = await self._redis.xautoclaim(
            self._stream, self.name, self._worker_id, self._reclaim_idle_ms, "0-0", count=count
        )
        claimed: list[Message] = result[1]
        return [entry for entry in claimed if entry[1]]

    async def _handle(self, message_id: str, fields: dict[str, str]) -> None:
        handler = self._handlers.get(fields["type"])
        if handler is not None:
            event = parse_event(fields["payload"])
            async with self._sessions() as session, session.begin():
                claimed = await session.execute(
                    insert(ProcessedEvent)
                    .values(consumer=self.name, event_id=UUID(fields["event_id"]))
                    .on_conflict_do_nothing()
                    .returning(ProcessedEvent.event_id)
                )
                if claimed.first() is None:
                    log.info("%s: skipping duplicate event %s", self.name, fields["event_id"])
                else:
                    await handler(session, event)
        await self._redis.xack(self._stream, self.name, message_id)
