from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import DateTime, Dialect, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import TypeDecorator

from riven_api.config import get_settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    """Stores UTC and always returns timezone-aware UTC (SQLite drops the offset otherwise)."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


@lru_cache
def _sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_demo_user(engine: AsyncEngine) -> None:
    """Create the development account once (see `Settings.demo_*`); no-op when disabled."""
    from riven_api.models import User
    from riven_api.security import hash_password

    settings = get_settings()
    if not settings.demo_user_active:
        return
    email = settings.demo_email.lower()
    async with async_sessionmaker(engine)() as session:
        if await session.scalar(select(User).where(User.email == email)):
            return
        session.add(
            User(
                email=email,
                name=settings.demo_username,
                password_hash=hash_password(settings.demo_password.get_secret_value()),
            )
        )
        await session.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependency: tests override it with an in-memory database."""
    async with _sessionmaker()() as session:
        yield session
