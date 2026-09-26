"""Alembic migrations (ticket S01.4). All schema changes go through here."""

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from riven_api.config import get_settings
from riven_api.db import Base
from riven_events import EventsBase

target_metadata = [Base.metadata, EventsBase.metadata]


def _url() -> str:
    """`sqlalchemy.url` set programmatically (tests) wins over settings."""
    return context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
