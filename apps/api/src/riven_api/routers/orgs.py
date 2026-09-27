"""Organizations, members and invitations (S03.2)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.deps import CurrentPrincipal
from riven_api.auth.org import CurrentOrg, TenantSession
from riven_api.config import get_settings
from riven_api.db import get_session
from riven_api.services import orgs
from riven_api.services.mail import Mailer, get_mailer
from riven_db.models import Repository, User
from riven_schemas import Role

router = APIRouter(prefix="/v1", tags=["organizations"])
Session = Annotated[AsyncSession, Depends(get_session)]
MANAGERS = {Role.OWNER, Role.ADMIN}


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    role: Role
    require_mfa: bool

    @classmethod
    def of(cls, found: orgs.OrgWithRole) -> "OrgOut":
        o = found.org
        return cls(id=o.id, name=o.name, slug=o.slug, role=found.role, require_mfa=o.require_mfa)


class MemberOut(BaseModel):
    user_id: UUID
    email: str
    name: str
    role: Role
    joined_at: datetime


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = Role.VIEWER


class InvitationOut(BaseModel):
    id: UUID
    email: str
    role: Role
    expires_at: datetime


class AcceptIn(BaseModel):
    token: str = Field(min_length=16, max_length=200)


class RepositoryOut(BaseModel):
    id: UUID
    full_name: str
    provider: str
    default_branch: str


def _require_manager(ctx: CurrentOrg) -> None:
    if ctx.role not in MANAGERS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")


@router.post("/orgs", status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgIn, principal: CurrentPrincipal, session: Session) -> OrgOut:
    """Create an organization; the caller becomes its owner."""
    created = await orgs.create_org(session, body.name, principal.id)
    await session.commit()
    return OrgOut.of(created)


@router.get("/orgs")
async def list_orgs(principal: CurrentPrincipal, session: Session) -> list[OrgOut]:
    """Organizations the caller belongs to."""
    return [OrgOut.of(found) for found in await orgs.orgs_of(session, principal.id)]


@router.get("/orgs/{org_id}")
async def get_org(ctx: CurrentOrg) -> OrgOut:
    return OrgOut.of(orgs.OrgWithRole(ctx.org, ctx.role))


@router.get("/orgs/{org_id}/members")
async def list_members(ctx: CurrentOrg, session: Session) -> list[MemberOut]:
    return [
        MemberOut(
            user_id=user.id,
            email=user.email,
            name=user.name,
            role=Role(m.role),
            joined_at=m.created_at,
        )
        for user, m in await orgs.members(session, ctx.org_id)
    ]


@router.post("/orgs/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite(
    body: InviteIn,
    ctx: CurrentOrg,
    session: Session,
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> InvitationOut:
    """Invite someone by email; they join with `role` when they accept."""
    _require_manager(ctx)
    if body.role is Role.OWNER and ctx.role is not Role.OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="only_owners_invite_owners")
    try:
        invitation, token = await orgs.invite(
            session, ctx.org_id, body.email, body.role, ctx.principal.id
        )
    except orgs.Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await session.commit()
    link = f"{get_settings().web_url}/invite?token={token}"
    await mailer.send(
        invitation.email,
        f"You're invited to {ctx.org.name} on Riven",
        f"{ctx.principal.name or ctx.principal.email} invited you to join {ctx.org.name} "
        f"as {body.role.value}.\n\nAccept the invitation: {link}\n\n"
        "The link expires in 7 days.",
    )
    return InvitationOut(
        id=invitation.id, email=invitation.email, role=body.role, expires_at=invitation.expires_at
    )


@router.get("/orgs/{org_id}/invitations")
async def list_invitations(ctx: CurrentOrg, session: Session) -> list[InvitationOut]:
    _require_manager(ctx)
    return [
        InvitationOut(id=i.id, email=i.email, role=Role(i.role), expires_at=i.expires_at)
        for i in await orgs.pending_invitations(session, ctx.org_id)
    ]


@router.delete("/orgs/{org_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(invitation_id: UUID, ctx: CurrentOrg, session: Session) -> Response:
    _require_manager(ctx)
    try:
        await orgs.revoke_invitation(session, ctx.org_id, invitation_id)
    except orgs.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return Response(status_code=204)


@router.post("/invitations/accept")
async def accept_invitation(
    body: AcceptIn, principal: CurrentPrincipal, session: Session
) -> OrgOut:
    """Join the org of an invitation sent to the caller's email."""
    user = await session.get(User, principal.id)
    assert user is not None
    try:
        joined = await orgs.accept(session, body.token, user)
    except orgs.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except orgs.Forbidden as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    await session.commit()
    return OrgOut.of(joined)


@router.get("/orgs/{org_id}/repositories")
async def list_repositories(session: TenantSession) -> list[RepositoryOut]:
    """Repositories of the org (read through row-level security)."""
    repos = await session.scalars(select(Repository).order_by(Repository.full_name))
    return [
        RepositoryOut(
            id=r.id, full_name=r.full_name, provider=r.provider, default_branch=r.default_branch
        )
        for r in repos
    ]
