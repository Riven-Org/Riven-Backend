"""S02.1.2: the seed loads the demo repo with bugs, locks and a consistent graph, and is
idempotent. Needs Postgres (RIVEN_TEST_DATABASE_URL)."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_db.models import Bug, Change, GraphEdge, RegressionLock, VerificationRun
from riven_db.seed import CHANGES, DEMO_ORG, seed
from riven_worker.graph_consistency import count_orphaned_edges


async def _count(session: AsyncSession, model: type) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def test_seed_loads_the_demo_repo_with_bugs_locks_and_graph(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        assert await seed(session) is True

    async with sessions() as session:
        assert await _count(session, Change) == len(CHANGES)
        assert await _count(session, VerificationRun) == len(CHANGES)
        assert await _count(session, Bug) == 1
        assert await _count(session, RegressionLock) == 1
        assert await _count(session, GraphEdge) == 7
        producers = set(await session.scalars(select(Change.producer_kind)))
        assert producers == {"human", "ai_agent", "bot"}
        assert {o for o in await session.scalars(select(Bug.org_id))} == {DEMO_ORG}


async def test_seeding_twice_changes_nothing(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        await seed(session)
    async with sessions() as session, session.begin():
        assert await seed(session) is False

    async with sessions() as session:
        assert await _count(session, Change) == len(CHANGES)


async def test_seeded_demo_graph_has_zero_orphaned_edges(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        await seed(session)

    async with sessions() as session:
        report = await count_orphaned_edges(session)

    assert report.checked_edges == 7
    assert report.orphaned_edges == 0
