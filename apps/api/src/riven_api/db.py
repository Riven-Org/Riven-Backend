from collections.abc import AsyncIterator
from datetime import datetime
from functools import lru_cache

from sqlalchemy import DateTime, String, func
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from riven_api.config import get_settings


class Base(DeclarativeBase):
    pass


class TenantMixin:
    """Every domain table is scoped to an org (tickets S01.4, S03.2)."""

    org_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_sessionmaker(get_engine(), expire_on_commit=False)() as session:
        yield session
