from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from riven_api.config import get_settings
from riven_db import Base, TenantMixin

__all__ = ["Base", "TenantMixin", "get_engine", "get_session"]


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session
