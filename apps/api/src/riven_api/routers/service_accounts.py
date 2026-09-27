"""Service accounts and API keys for AI agents and CI (S03.4)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.access import PermissionedRoute, Requires
from riven_api.auth.org import OrgContext
from riven_api.auth.permissions import Permission
from riven_api.db import get_session
from riven_api.services import api_keys
from riven_db.models import ApiKey, ServiceAccount

router = APIRouter(prefix="/v1", tags=["service accounts"], route_class=PermissionedRoute)
Session = Annotated[AsyncSession, Depends(get_session)]
Manage = Annotated[OrgContext, Requires(Permission.API_KEYS_MANAGE)]
P = Permission

DEFAULT_SCOPES = {
    "ai_agent": [P.CHANGES_SUBMIT, P.CHANGES_READ, P.RUNS_READ],
    "ci": [P.CHANGES_SUBMIT, P.CHANGES_READ, P.RUNS_READ, P.RUNS_CANCEL],
    "bot": [P.CHANGES_SUBMIT, P.CHANGES_READ],
}


class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=100, pattern=r"^[A-Za-z0-9._-]+$")
    kind: Literal["ai_agent", "ci", "bot"]
    agent_model: str | None = Field(default=None, max_length=128)


class KeyIn(BaseModel):
    scopes: list[Permission] | None = Field(
        default=None, description="Defaults to the usual scopes for the account's kind"
    )
    expires_in_days: int | None = Field(default=90, ge=1, le=365)


class KeyOut(BaseModel):
    id: UUID
    prefix: str
    scopes: list[str]
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None

    @classmethod
    def of(cls, key: ApiKey) -> "KeyOut":
        return cls(
            id=key.id,
            prefix=f"rvn_{key.prefix}",
            scopes=key.scopes,
            created_at=key.created_at,
            expires_at=key.expires_at,
            last_used_at=key.last_used_at,
        )


class IssuedKeyOut(KeyOut):
    secret: str = Field(description="The full API key. Shown once; store it now.")


class AccountOut(BaseModel):
    id: UUID
    name: str
    kind: str
    agent_model: str | None
    created_at: datetime
    keys: list[KeyOut]

    @classmethod
    def of(cls, account: ServiceAccount, keys: list[ApiKey]) -> "AccountOut":
        return cls(
            id=account.id,
            name=account.name,
            kind=account.kind,
            agent_model=account.agent_model,
            created_at=account.created_at,
            keys=[KeyOut.of(k) for k in keys],
        )


def _not_found(exc: LookupError) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


async def _issue(
    session: AsyncSession,
    ctx: OrgContext,
    account: ServiceAccount,
    scopes: list[str],
    expires_at: datetime | None,
) -> IssuedKeyOut:
    beyond = set(scopes) - {p.value for p in ctx.permissions}
    if beyond:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"cannot_grant:{','.join(sorted(beyond))}"
        )
    issued = await api_keys.issue(
        session, account, scopes=scopes, expires_at=expires_at, created_by=ctx.principal.id
    )
    await session.commit()
    return IssuedKeyOut(**KeyOut.of(issued.key).model_dump(), secret=issued.secret)


@router.get("/orgs/{org_id}/service-accounts")
async def list_accounts(
    ctx: Annotated[OrgContext, Requires(P.API_KEYS_READ)], session: Session
) -> list[AccountOut]:
    """Service accounts and their active keys (never the secrets)."""
    return [AccountOut.of(a, k) for a, k in await api_keys.accounts_with_keys(session, ctx.org_id)]


@router.post("/orgs/{org_id}/service-accounts", status_code=201)
async def create_account(body: AccountIn, ctx: Manage, session: Session) -> AccountOut:
    if ctx.principal.kind != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="users_only")
    account = ServiceAccount(
        org_id=ctx.org_id,
        name=body.name,
        kind=body.kind,
        agent_model=body.agent_model,
        created_by=ctx.principal.id,
    )
    session.add(account)
    await session.commit()
    return AccountOut.of(account, [])


@router.delete("/orgs/{org_id}/service-accounts/{account_id}", status_code=204)
async def disable_account(account_id: UUID, ctx: Manage, session: Session) -> Response:
    """Disable the account and revoke all its keys."""
    try:
        account = await api_keys.get_account(session, ctx.org_id, account_id)
    except LookupError as exc:
        raise _not_found(exc) from exc
    await api_keys.disable_account(session, account)
    await session.commit()
    return Response(status_code=204)


@router.post("/orgs/{org_id}/service-accounts/{account_id}/keys", status_code=201)
async def create_key(account_id: UUID, body: KeyIn, ctx: Manage, session: Session) -> IssuedKeyOut:
    """Issue a key. The response is the only time the secret is visible."""
    if ctx.principal.kind != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="users_only")
    try:
        account = await api_keys.get_account(session, ctx.org_id, account_id)
    except LookupError as exc:
        raise _not_found(exc) from exc
    scopes = [s.value for s in (body.scopes or DEFAULT_SCOPES[account.kind])]
    expires_at = (
        datetime.now(UTC) + timedelta(days=body.expires_in_days) if body.expires_in_days else None
    )
    return await _issue(session, ctx, account, scopes, expires_at)


@router.post("/orgs/{org_id}/api-keys/{key_id}/rotate", status_code=201)
async def rotate_key(key_id: UUID, ctx: Manage, session: Session) -> IssuedKeyOut:
    """Replace a key with a new secret (same scopes and lifetime); the old one stops working."""
    if ctx.principal.kind != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="users_only")
    try:
        old = await api_keys.get_key(session, ctx.org_id, key_id)
        account = await api_keys.get_account(session, ctx.org_id, old.service_account_id)
    except LookupError as exc:
        raise _not_found(exc) from exc
    lifetime = old.expires_at - old.created_at if old.expires_at else None
    await api_keys.revoke(session, old)
    expires_at = datetime.now(UTC) + lifetime if lifetime else None
    return await _issue(session, ctx, account, list(old.scopes), expires_at)


@router.delete("/orgs/{org_id}/api-keys/{key_id}", status_code=204)
async def revoke_key(key_id: UUID, ctx: Manage, session: Session) -> Response:
    try:
        key = await api_keys.get_key(session, ctx.org_id, key_id)
    except LookupError as exc:
        raise _not_found(exc) from exc
    await api_keys.revoke(session, key)
    await session.commit()
    return Response(status_code=204)
