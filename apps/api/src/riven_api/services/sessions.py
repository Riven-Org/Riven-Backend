"""Revoked IdP sessions (S03.5.3)."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from riven_db.models import RevokedSession

# Longer than any access token lives (5 min) or a refresh can extend a session (10 h).
REMEMBER_FOR = timedelta(hours=12)


async def is_revoked(session: AsyncSession, session_id: str) -> bool:
    found = await session.scalar(
        select(RevokedSession.session_id).where(
            RevokedSession.session_id == session_id,
            RevokedSession.expires_at > datetime.now(UTC),
        )
    )
    return found is not None


async def remember_revoked(session: AsyncSession, session_id: str, user_id: UUID) -> None:
    now = datetime.now(UTC)
    await session.execute(delete(RevokedSession).where(RevokedSession.expires_at <= now))
    await session.execute(
        insert(RevokedSession)
        .values(session_id=session_id, user_id=user_id, expires_at=now + REMEMBER_FOR)
        .on_conflict_do_nothing()
    )
