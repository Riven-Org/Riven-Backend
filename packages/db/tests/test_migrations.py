"""S01.4 acceptance: every schema change goes through migrations; every domain table has an
indexed org_id. Needs Postgres (RIVEN_TEST_DATABASE_URL)."""

import asyncio
from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from riven_db import Base
from riven_events import EventsBase

import riven_db.models  # noqa: F401  isort: skip


def _diff(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(connection)
    return list(compare_metadata(context, [Base.metadata, EventsBase.metadata]))


async def test_fresh_database_at_head_matches_the_models(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        diff = await conn.run_sync(_diff)

    assert diff == [], (
        "Models and migrations differ; add an Alembic migration (`<ID>: ...`) for:\n"
        + "\n".join(map(str, diff))
    )


def _org_id_report(connection: Connection) -> dict[str, str]:
    inspector = inspect(connection)
    problems = {}
    for table in Base.metadata.sorted_tables:
        columns = {c["name"]: c for c in inspector.get_columns(table.name)}
        if "org_id" not in columns:
            problems[table.name] = "no org_id column"
        elif columns["org_id"]["nullable"]:
            problems[table.name] = "org_id is nullable"
        elif not any(
            ix["column_names"][:1] == ["org_id"] for ix in inspector.get_indexes(table.name)
        ):
            problems[table.name] = "org_id is not indexed"
    return problems


async def test_every_domain_table_has_an_indexed_non_null_org_id(db_engine: AsyncEngine) -> None:
    async with db_engine.connect() as conn:
        problems = await conn.run_sync(_org_id_report)

    assert len(Base.metadata.sorted_tables) >= 8
    assert problems == {}


def test_migrations_downgrade_to_base_and_upgrade_again(migrated_database: str) -> None:
    from conftest import ALEMBIC_INI

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", migrated_database)

    command.downgrade(config, "base")
    command.upgrade(config, "head")

    async def diff() -> list[Any]:
        engine = create_async_engine(migrated_database, poolclass=NullPool)
        async with engine.connect() as conn:
            result = await conn.run_sync(_diff)
        await engine.dispose()
        return result

    assert asyncio.run(diff()) == []
