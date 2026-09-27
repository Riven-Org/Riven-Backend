"""Organizations, members and invitations (S03.2)."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.access import PermissionedRoute, Requires
from riven_api.auth.deps import CurrentUser
from riven_api.auth.org import OrgContext, TenantSession
from riven_api.auth.permissions import MATRIX, Permission
from riven_api.config import get_settings
from riven_api.db import get_session
from riven_api.services import orgs
from riven_api.services.idp_admin import IdpAdmin, get_idp_admin
from riven_api.services.mail import Mailer, get_mailer
from riven_db.models import Organization, Repository, User
from riven_schemas import Role

router = APIRouter(prefix="/v1", tags=["organizations"], route_class=PermissionedRoute)
Session = Annotated[AsyncSession, Depends(get_session)]
P = Permission


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    role: Role | None = Field(description="The caller's role; null for service accounts")
    require_mfa: bool
    permissions: list[Permission] = Field(description="What the caller may do in this org")

    @classmethod
    def of(cls, found: orgs.OrgWithRole) -> "OrgOut":
        return cls.build(found.org, found.role, MATRIX[found.role])

    @classmethod
    def build(
        cls, org: Organization, role: Role | None, permissions: frozenset[Permission]
    ) -> "OrgOut":
        return cls(
            id=org.id,
            name=org.name,
            slug=org.slug,
            role=role,
            require_mfa=org.require_mfa,
            permissions=sorted(permissions),
        )


class OrgUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class RoleIn(BaseModel):
    role: Role


class SecurityPolicyIn(BaseModel):
    require_mfa: bool


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


def _raise(exc: Exception) -> HTTPException:
    code = {
        orgs.NotFound: status.HTTP_404_NOT_FOUND,
        orgs.Forbidden: status.HTTP_403_FORBIDDEN,
        orgs.Conflict: status.HTTP_409_CONFLICT,
    }[type(exc)]
    return HTTPException(code, detail=str(exc))


@router.post("/orgs", status_code=status.HTTP_201_CREATED)
async def create_org(body: OrgIn, principal: CurrentUser, session: Session) -> OrgOut:
    """Create an organization; the caller becomes its owner."""
    created = await orgs.create_org(session, body.name, principal.id)
    await session.commit()
    return OrgOut.of(created)


@router.get("/orgs")
async def list_orgs(principal: CurrentUser, session: Session) -> list[OrgOut]:
    """Organizations the caller belongs to."""
    return [OrgOut.of(found) for found in await orgs.orgs_of(session, principal.id)]


@router.get("/orgs/{org_id}")
async def get_org(ctx: Annotated[OrgContext, Requires(P.ORG_READ)]) -> OrgOut:
    return OrgOut.build(ctx.org, ctx.role, ctx.permissions)


@router.patch("/orgs/{org_id}")
async def rename_org(
    body: OrgUpdate, ctx: Annotated[OrgContext, Requires(P.ORG_UPDATE)], session: Session
) -> OrgOut:
    org = await orgs.rename(session, ctx.org_id, body.name)
    await session.commit()
    return OrgOut.build(org, ctx.role, ctx.permissions)


@router.patch("/orgs/{org_id}/security")
async def update_security_policy(
    body: SecurityPolicyIn,
    ctx: Annotated[OrgContext, Requires(P.ORG_SECURITY)],
    session: Session,
    idp: Annotated[IdpAdmin, Depends(get_idp_admin)],
) -> OrgOut:
    """Require every member to use two-factor authentication. Members without it are asked
    to enrol at their next sign-in and get `mfa_required` until they do."""
    if body.require_mfa and not await idp.has_mfa(ctx.principal.subject):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="enable_mfa_first")
    org = await session.get(Organization, ctx.org_id)
    assert org is not None
    org.require_mfa = body.require_mfa
    await session.commit()
    return OrgOut.build(org, ctx.role, ctx.permissions)


@router.get("/orgs/{org_id}/members")
async def list_members(
    ctx: Annotated[OrgContext, Requires(P.MEMBERS_READ)], session: Session
) -> list[MemberOut]:
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


@router.patch("/orgs/{org_id}/members/{user_id}")
async def change_role(
    user_id: UUID,
    body: RoleIn,
    ctx: Annotated[OrgContext, Requires(P.MEMBERS_UPDATE_ROLE)],
    session: Session,
) -> MemberOut:
    try:
        membership = await orgs.set_role(session, ctx.org_id, user_id, body.role, ctx.role)
    except (orgs.NotFound, orgs.Forbidden, orgs.Conflict) as exc:
        raise _raise(exc) from exc
    await session.commit()
    user = await session.get(User, user_id)
    assert user is not None
    return MemberOut(
        user_id=user.id,
        email=user.email,
        name=user.name,
        role=Role(membership.role),
        joined_at=membership.created_at,
    )


@router.delete("/orgs/{org_id}/members/{user_id}", status_code=204)
async def remove_member(
    user_id: UUID, ctx: Annotated[OrgContext, Requires(P.MEMBERS_REMOVE)], session: Session
) -> Response:
    try:
        await orgs.remove_member(session, ctx.org_id, user_id, ctx.role)
    except (orgs.NotFound, orgs.Forbidden, orgs.Conflict) as exc:
        raise _raise(exc) from exc
    await session.commit()
    return Response(status_code=204)


@router.post("/orgs/{org_id}/invitations", status_code=status.HTTP_201_CREATED)
async def invite(
    body: InviteIn,
    ctx: Annotated[OrgContext, Requires(P.MEMBERS_INVITE)],
    session: Session,
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> InvitationOut:
    """Invite someone by email; they join with `role` when they accept."""
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
async def list_invitations(
    ctx: Annotated[OrgContext, Requires(P.MEMBERS_INVITE)], session: Session
) -> list[InvitationOut]:
    return [
        InvitationOut(id=i.id, email=i.email, role=Role(i.role), expires_at=i.expires_at)
        for i in await orgs.pending_invitations(session, ctx.org_id)
    ]


@router.delete("/orgs/{org_id}/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: UUID, ctx: Annotated[OrgContext, Requires(P.MEMBERS_INVITE)], session: Session
) -> Response:
    try:
        await orgs.revoke_invitation(session, ctx.org_id, invitation_id)
    except orgs.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return Response(status_code=204)


@router.post("/invitations/accept")
async def accept_invitation(body: AcceptIn, principal: CurrentUser, session: Session) -> OrgOut:
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
async def list_repositories(
    _: Annotated[OrgContext, Requires(P.REPOS_READ)], session: TenantSession
) -> list[RepositoryOut]:
    """Repositories of the org (read through row-level security)."""
    repos = await session.scalars(select(Repository).order_by(Repository.full_name))
    return [
        RepositoryOut(
            id=r.id, full_name=r.full_name, provider=r.provider, default_branch=r.default_branch
        )
        for r in repos
    ]
