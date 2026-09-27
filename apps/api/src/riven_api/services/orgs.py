"""Organizations, memberships and invitations (S03.2.1)."""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_db.models import Invitation, Membership, Organization, User
from riven_schemas import Role

INVITATION_TTL = timedelta(days=7)


class NotFound(Exception):
    pass


class Forbidden(Exception):
    pass


class Conflict(Exception):
    pass


@dataclass(frozen=True)
class OrgWithRole:
    org: Organization
    role: Role


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "org"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_org(session: AsyncSession, name: str, owner: UUID) -> OrgWithRole:
    base = _slugify(name)
    taken = set(
        await session.scalars(select(Organization.slug).where(Organization.slug.like(f"{base}%")))
    )
    slug, n = base, 1
    while slug in taken:
        n += 1
        slug = f"{base}-{n}"
    org = Organization(id=f"org_{secrets.token_hex(6)}", name=name.strip(), slug=slug)
    session.add(org)
    await session.flush()
    session.add(Membership(org_id=org.id, user_id=owner, role=Role.OWNER.value))
    await session.flush()
    return OrgWithRole(org, Role.OWNER)


async def orgs_of(session: AsyncSession, user_id: UUID) -> list[OrgWithRole]:
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user_id)
        .order_by(Organization.name)
    )
    return [OrgWithRole(org, Role(role)) for org, role in rows.all()]


async def membership(session: AsyncSession, org_id: str, user_id: UUID) -> OrgWithRole | None:
    row = (
        await session.execute(
            select(Organization, Membership.role)
            .join(Membership, Membership.org_id == Organization.id)
            .where(Membership.org_id == org_id, Membership.user_id == user_id)
        )
    ).first()
    return OrgWithRole(row[0], Role(row[1])) if row else None


async def members(session: AsyncSession, org_id: str) -> list[tuple[User, Membership]]:
    rows = await session.execute(
        select(User, Membership)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.org_id == org_id)
        .order_by(User.email)
    )
    return [(u, m) for u, m in rows.all()]


async def invite(
    session: AsyncSession, org_id: str, email: str, role: Role, invited_by: UUID
) -> tuple[Invitation, str]:
    """Create an invitation; returns it with the one-time token to email."""
    email = email.strip().lower()
    already = await session.scalar(
        select(func.count())
        .select_from(Membership)
        .join(User, User.id == Membership.user_id)
        .where(Membership.org_id == org_id, func.lower(User.email) == email)
    )
    if already:
        raise Conflict("already_a_member")
    token = secrets.token_urlsafe(32)
    invitation = Invitation(
        org_id=org_id,
        email=email,
        role=role.value,
        token_hash=hash_token(token),
        invited_by=invited_by,
        expires_at=datetime.now(UTC) + INVITATION_TTL,
    )
    session.add(invitation)
    await session.flush()
    return invitation, token


async def pending_invitations(session: AsyncSession, org_id: str) -> list[Invitation]:
    return list(
        await session.scalars(
            select(Invitation)
            .where(
                Invitation.org_id == org_id,
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
            .order_by(Invitation.created_at.desc())
        )
    )


async def revoke_invitation(session: AsyncSession, org_id: str, invitation_id: UUID) -> None:
    invitation = await session.scalar(
        select(Invitation).where(Invitation.org_id == org_id, Invitation.id == invitation_id)
    )
    if invitation is None or invitation.accepted_at is not None:
        raise NotFound("invitation_not_found")
    invitation.revoked_at = datetime.now(UTC)


async def accept(session: AsyncSession, token: str, user: User) -> OrgWithRole:
    invitation = await session.scalar(
        select(Invitation).where(Invitation.token_hash == hash_token(token))
    )
    now = datetime.now(UTC)
    if (
        invitation is None
        or invitation.revoked_at is not None
        or invitation.accepted_at is not None
        or invitation.expires_at <= now
    ):
        raise NotFound("invitation_not_found")
    if invitation.email != user.email.lower():
        raise Forbidden("invitation_for_another_email")
    existing = await membership(session, invitation.org_id, user.id)
    if existing is None:
        session.add(Membership(org_id=invitation.org_id, user_id=user.id, role=invitation.role))
    invitation.accepted_at, invitation.accepted_by = now, user.id
    await session.flush()
    joined = await membership(session, invitation.org_id, user.id)
    assert joined is not None
    return joined
