from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from riven_api.config import get_settings
from riven_db import Base, TenantMixin

__all__ = ["Base", "TenantMixin", "get_engine", "get_session", "get_sessionmaker"]


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url.get_secret_value(), pool_pre_ping=True)


@lru_cache
def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Dependency: tests override it to point at the test database."""
    return _sessionmaker()


async def get_session(
    sessions: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> AsyncIterator[AsyncSession]:
    async with sessions() as session:
        yield session
