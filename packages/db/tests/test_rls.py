"""S03.2.2: Postgres row-level security enforces org_id on every tenant table.
Needs Postgres (RIVEN_TEST_DATABASE_URL)."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from riven_db import tenant_tables
from riven_db.models import Repository
from riven_db.rls import APP_ROLE, tenant_session


async def _repos(sessions: async_sessionmaker[AsyncSession]) -> None:
    """System (login role) writes one repository per org."""
    async with sessions() as session, session.begin():
        session.add_all(
            [
                Repository(org_id="org_a", full_name="acme/shop"),
                Repository(org_id="org_b", full_name="globex/api"),
            ]
        )


async def test_every_tenant_table_has_rls_and_the_tenant_policy(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        rows = await conn.execute(text("SELECT relname FROM pg_class WHERE relrowsecurity"))
        secured = set(rows.scalars())
        with_policy = set(
            (
                await conn.execute(
                    text("SELECT tablename FROM pg_policies WHERE policyname = 'tenant_isolation'")
                )
            ).scalars()
        )

    expected = {t.name for t in tenant_tables()}
    missing = expected - secured
    assert missing == set(), f"tenant tables without RLS (call enable_rls()): {missing}"
    assert expected - with_policy == set()


async def test_tenant_session_only_sees_its_org(sessions: async_sessionmaker[AsyncSession]) -> None:
    await _repos(sessions)

    async with tenant_session(sessions, "org_a") as session:
        names = list(await session.scalars(select(Repository.full_name)))

    assert names == ["acme/shop"]


async def test_query_without_org_context_returns_zero_rows(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _repos(sessions)

    async with sessions() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        count = await session.scalar(select(func.count()).select_from(Repository))

    assert count == 0


async def test_writing_another_orgs_row_is_rejected(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(DBAPIError, match="row-level security"):
        async with tenant_session(sessions, "org_a") as session, session.begin():
            session.add(Repository(org_id="org_b", full_name="sneaky/write"))


async def test_org_context_does_not_leak_to_the_next_user_of_a_pooled_connection(
    migrated_database: str,
) -> None:
    engine = create_async_engine(migrated_database, pool_size=1, max_overflow=0)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _repos(sessions)
        async with tenant_session(sessions, "org_a") as session:
            await session.scalar(select(func.count()).select_from(Repository))
            await session.commit()

        async with sessions() as session:  # same physical connection, no org context
            role = await session.scalar(text("SELECT current_user"))
            org = await session.scalar(text("SELECT current_setting('app.org_id', true)"))
            count = await session.scalar(select(func.count()).select_from(Repository))
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE repositories CASCADE"))
        await engine.dispose()

    assert role != APP_ROLE
    assert not org
    assert count == 2  # the system role sees everything; no context was left behind


async def test_every_transaction_in_a_tenant_session_keeps_the_context(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _repos(sessions)

    async with tenant_session(sessions, "org_b") as session:
        first = list(await session.scalars(select(Repository.full_name)))
        await session.commit()
        second = list(await session.scalars(select(Repository.full_name)))

    assert first == second == ["globex/api"]
