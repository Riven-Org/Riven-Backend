"""Shared fixtures for tests that need real Postgres / Redis.

Set RIVEN_TEST_DATABASE_URL (CI does) to run database tests; without it they are skipped.
The database is reset and migrated to head once per session, and every table is emptied
after each test. RIVEN_TEST_REDIS_URL selects a real Redis; otherwise fakeredis is used.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

ALEMBIC_INI = Path(__file__).parent / "apps/api/alembic.ini"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    url = os.environ.get("RIVEN_TEST_DATABASE_URL")
    if not url:
        pytest.skip("RIVEN_TEST_DATABASE_URL not set")
    yield url


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    async def reset() -> None:
        engine = create_async_engine(database_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(reset())
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    return database_url


@pytest.fixture
async def db_engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    yield engine
    async with engine.begin() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT string_agg(format('%I', tablename), ', ') FROM pg_tables "
                    "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                )
            )
        ).scalar_one()
        if tables:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest.fixture
def sessions(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    url = os.environ.get("RIVEN_TEST_REDIS_URL")
    if url:
        client: Redis = Redis.from_url(url, decode_responses=True)
        await client.flushdb()
    else:
        import fakeredis

        client = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()
