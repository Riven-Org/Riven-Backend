"""Outbox relay: publish committed outbox rows to a Redis Stream (S01.3.1).

Run with `python -m riven_events.relay`. Rows are claimed with FOR UPDATE SKIP LOCKED, so
several relays can run side by side. A row is marked published only after XADD succeeds; if
the relay dies in between, the row is published again on restart (at-least-once), and
consumers drop the duplicate by event ID.
"""

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from riven_events.config import EventSettings
from riven_events.models import OutboxEvent

STREAM = "riven:events"
log = logging.getLogger(__name__)


class OutboxRelay:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        redis: "Redis",
        *,
        stream: str = STREAM,
        batch_size: int = 100,
    ) -> None:
        self._sessions = sessions
        self._redis = redis
        self._stream = stream
        self._batch_size = batch_size

    async def relay_once(self) -> int:
        """Publish one batch of unpublished events; return how many were published."""
        async with self._sessions() as session, session.begin():
            rows = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.published_at.is_(None))
                    .order_by(OutboxEvent.id)
                    .limit(self._batch_size)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                await self._redis.xadd(
                    self._stream,
                    {
                        "event_id": str(row.event_id),
                        "type": row.event_type,
                        "org_id": row.org_id,
                        "payload": json.dumps(row.payload),
                    },
                )
                row.published_at = datetime.now(UTC)
            return len(rows)

    async def run(self, *, poll_seconds: float = 0.5, stop: asyncio.Event | None = None) -> None:
        stop = stop or asyncio.Event()
        while not stop.is_set():
            try:
                published = await self.relay_once()
            except Exception:
                log.exception("outbox relay batch failed; retrying")
                published = 0
            if published == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=poll_seconds)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = EventSettings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    relay = OutboxRelay(async_sessionmaker(engine, expire_on_commit=False), redis)
    log.info("outbox relay publishing to %s", STREAM)
    await relay.run(poll_seconds=settings.outbox_poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
