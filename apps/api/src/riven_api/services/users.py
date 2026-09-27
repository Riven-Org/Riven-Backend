from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.tokens import TokenClaims
from riven_db.models import User

TOUCH_EVERY = timedelta(minutes=5)


async def get_or_provision(session: AsyncSession, claims: TokenClaims) -> User:
    """Find the user for this IdP subject, creating it on first sign-in (JIT provisioning)."""
    user = await session.scalar(select(User).where(User.idp_subject == claims.subject))
    now = datetime.now(UTC)
    if user is None:
        user = User(
            idp_subject=claims.subject, email=claims.email, name=claims.name, last_seen_at=now
        )
        session.add(user)
        await session.flush()
        return user
    if user.email != claims.email or user.name != claims.name:
        user.email, user.name = claims.email, claims.name
    if now - user.last_seen_at > TOUCH_EVERY:
        user.last_seen_at = now
    return user
