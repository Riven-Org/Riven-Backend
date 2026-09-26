"""S01.3 acceptance: outbox in the state change's transaction, at-least-once delivery,
idempotent consumers. Needs Postgres (RIVEN_TEST_DATABASE_URL); Redis may be fakeredis."""

import asyncio
import time
from typing import Any

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_events import STREAM, EventConsumer, OutboxEvent, OutboxRelay, add_event
from riven_schemas import BugConfirmed, ChangeRef, DomainEvent

CHANGE = ChangeRef(org_id="org_a", repo="acme/shop", commit_sha="abc123")


def _bug_event(bug_id: str = "bug_1") -> BugConfirmed:
    return BugConfirmed(change=CHANGE, bug_id=bug_id, fingerprint=f"fp-{bug_id}")


async def _create_demo_tables(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await session.execute(text("CREATE TABLE IF NOT EXISTS demo_bugs (id text PRIMARY KEY)"))
        await session.execute(
            text("CREATE TABLE IF NOT EXISTS demo_effects (id serial PRIMARY KEY, bug_id text)")
        )


async def _confirm_bug(sessions: async_sessionmaker[AsyncSession], event: BugConfirmed) -> None:
    """A state change plus its event, in one transaction."""
    async with sessions() as session, session.begin():
        await session.execute(text("INSERT INTO demo_bugs VALUES (:id)"), {"id": event.bug_id})
        add_event(session, event, org_id=event.change.org_id)


async def _count(sessions: async_sessionmaker[AsyncSession], sql: str) -> int:
    async with sessions() as session:
        return int((await session.execute(text(sql))).scalar_one())


async def _stream_event_ids(redis: Redis) -> list[str]:
    return [fields["event_id"] for _id, fields in await redis.xrange(STREAM)]


async def _record_effect(session: AsyncSession, event: DomainEvent) -> None:
    assert isinstance(event, BugConfirmed)
    await session.execute(
        text("INSERT INTO demo_effects (bug_id) VALUES (:b)"), {"b": event.bug_id}
    )


class FlakyRedis:
    """Delegates to a real client but fails a chosen command after N successful calls."""

    def __init__(self, inner: Redis, command: str, fail_after: int) -> None:
        self._inner = inner
        self._command = command
        self._remaining = fail_after

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name != self._command:
            return attr

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            if self._remaining == 0:
                raise ConnectionError(f"simulated crash during {name}")
            self._remaining -= 1
            return await attr(*args, **kwargs)

        return wrapped


# --- outbox ------------------------------------------------------------------------------


async def test_event_is_stored_in_the_same_transaction_as_the_state_change(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _create_demo_tables(sessions)

    await _confirm_bug(sessions, _bug_event())

    assert await _count(sessions, "SELECT count(*) FROM demo_bugs") == 1
    assert await _count(sessions, "SELECT count(*) FROM outbox_events") == 1


async def test_event_is_discarded_when_the_state_change_rolls_back(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _create_demo_tables(sessions)

    with pytest.raises(RuntimeError):
        async with sessions() as session, session.begin():
            await session.execute(text("INSERT INTO demo_bugs VALUES ('bug_1')"))
            add_event(session, _bug_event(), org_id="org_a")
            await session.flush()
            raise RuntimeError("business rule failed after the event was staged")

    assert await _count(sessions, "SELECT count(*) FROM demo_bugs") == 0
    assert await _count(sessions, "SELECT count(*) FROM outbox_events") == 0


# --- relay -------------------------------------------------------------------------------


async def test_relay_publishes_a_committed_event_within_two_seconds(
    sessions: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    await _create_demo_tables(sessions)
    stop = asyncio.Event()
    relay_task = asyncio.create_task(OutboxRelay(sessions, redis).run(poll_seconds=0.5, stop=stop))
    await asyncio.sleep(0.1)  # relay is idle, waiting for work

    event = _bug_event()
    await _confirm_bug(sessions, event)
    committed = time.monotonic()
    while not await _stream_event_ids(redis):
        assert time.monotonic() - committed < 2.0, "event not published within 2s of commit"
        await asyncio.sleep(0.02)
    latency = time.monotonic() - committed

    stop.set()
    await relay_task
    assert await _stream_event_ids(redis) == [str(event.event_id)]
    assert latency < 2.0


async def test_relay_restart_after_a_crash_loses_no_event(
    sessions: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    await _create_demo_tables(sessions)
    events = [_bug_event(f"bug_{i}") for i in range(3)]
    for event in events:
        await _confirm_bug(sessions, event)

    # Crash after the first XADD: nothing gets marked published, one event already went out.
    with pytest.raises(ConnectionError):
        await OutboxRelay(sessions, FlakyRedis(redis, "xadd", fail_after=1)).relay_once()  # type: ignore[arg-type]
    unpublished_sql = "SELECT count(*) FROM outbox_events WHERE published_at IS NULL"
    assert await _count(sessions, unpublished_sql) == 3

    assert await OutboxRelay(sessions, redis).relay_once() == 3

    published = await _stream_event_ids(redis)
    assert set(published) == {str(e.event_id) for e in events}
    assert len(published) == 4  # at-least-once: the first event went out twice
    async with sessions() as session:
        unpublished = await session.scalar(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.published_at.is_(None))
        )
    assert unpublished == 0


# --- consumer ----------------------------------------------------------------------------


async def test_replaying_the_stream_causes_no_duplicate_side_effects(
    sessions: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    await _create_demo_tables(sessions)
    for i in range(2):
        await _confirm_bug(sessions, _bug_event(f"bug_{i}"))
    await OutboxRelay(sessions, redis).relay_once()
    consumer = EventConsumer("graph", sessions, redis, {"bug.confirmed": _record_effect})
    assert await consumer.process_once() == 2

    # Replay: publish every message again, as a relay restart or manual replay would.
    for _id, fields in await redis.xrange(STREAM):
        await redis.xadd(STREAM, fields)
    assert await consumer.process_once() == 2

    assert await _count(sessions, "SELECT count(*) FROM demo_effects") == 2
    assert await _count(sessions, "SELECT count(*) FROM processed_events") == 2


async def test_crash_before_ack_redelivers_without_a_second_side_effect(
    sessions: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    await _create_demo_tables(sessions)
    await _confirm_bug(sessions, _bug_event())
    await OutboxRelay(sessions, redis).relay_once()

    crashing = EventConsumer(
        "memory",
        sessions,
        FlakyRedis(redis, "xack", fail_after=0),  # type: ignore[arg-type]
        {"bug.confirmed": _record_effect},
        worker_id="w1",
    )
    with pytest.raises(ConnectionError):
        await crashing.process_once()
    assert await _count(sessions, "SELECT count(*) FROM demo_effects") == 1

    # Another worker takes over the unacknowledged message.
    survivor = EventConsumer(
        "memory",
        sessions,
        redis,
        {"bug.confirmed": _record_effect},
        worker_id="w2",
        reclaim_idle_ms=0,
    )
    assert await survivor.process_once() == 1

    assert await _count(sessions, "SELECT count(*) FROM demo_effects") == 1
    pending = await redis.xpending(STREAM, "memory")
    assert pending["pending"] == 0


async def test_failed_handler_leaves_no_trace_and_the_event_is_retried(
    sessions: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    await _create_demo_tables(sessions)
    await _confirm_bug(sessions, _bug_event())
    await OutboxRelay(sessions, redis).relay_once()

    async def broken(session: AsyncSession, event: DomainEvent) -> None:
        await _record_effect(session, event)
        raise ValueError("handler bug")

    with pytest.raises(ValueError):
        await EventConsumer("graph", sessions, redis, {"bug.confirmed": broken}).process_once()
    assert await _count(sessions, "SELECT count(*) FROM demo_effects") == 0
    assert await _count(sessions, "SELECT count(*) FROM processed_events") == 0

    fixed = EventConsumer(
        "graph", sessions, redis, {"bug.confirmed": _record_effect}, reclaim_idle_ms=0
    )
    assert await fixed.process_once() == 1
    assert await _count(sessions, "SELECT count(*) FROM demo_effects") == 1


async def test_events_without_a_handler_are_acknowledged_and_skipped(
    sessions: async_sessionmaker[AsyncSession], redis: Redis
) -> None:
    await _create_demo_tables(sessions)
    await _confirm_bug(sessions, _bug_event())
    await OutboxRelay(sessions, redis).relay_once()

    consumer = EventConsumer("notifications", sessions, redis, {})
    assert await consumer.process_once() == 1

    assert (await redis.xpending(STREAM, "notifications"))["pending"] == 0
    assert await _count(sessions, "SELECT count(*) FROM processed_events") == 0
