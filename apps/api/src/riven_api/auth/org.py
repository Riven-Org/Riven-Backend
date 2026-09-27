"""Org context for `/v1/orgs/{org_id}/...` endpoints (S03.2).

Callers who are not members get 404, not 403, so org ids cannot be probed. Domain data is
read through `TenantSession`, which row-level security confines to the org.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_api.auth.deps import CurrentPrincipal, Principal
from riven_api.auth.permissions import MATRIX, Permission
from riven_api.db import get_session, get_sessionmaker
from riven_api.services import orgs
from riven_db.models import Organization
from riven_db.rls import tenant_session
from riven_schemas import Role

_KNOWN = {p.value for p in Permission}


@dataclass(frozen=True)
class OrgContext:
    org: Organization
    role: Role | None  # None for service accounts, which act through key scopes
    principal: Principal

    @property
    def org_id(self) -> str:
        return self.org.id

    @property
    def permissions(self) -> frozenset[Permission]:
        if self.role is None:
            return frozenset(Permission(s) for s in self.principal.scopes if s in _KNOWN)
        return MATRIX[self.role]

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


def org_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail="org_not_found")


async def org_context(
    org_id: Annotated[str, Path(max_length=64)],
    principal: CurrentPrincipal,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrgContext:
    if principal.kind == "service_account":
        org = await session.get(Organization, org_id) if principal.org_id == org_id else None
        if org is None:
            raise org_not_found()
        return OrgContext(org=org, role=None, principal=principal)
    found = await orgs.membership(session, org_id, principal.id)
    if found is None:
        raise org_not_found()
    return OrgContext(org=found.org, role=found.role, principal=principal)


CurrentOrg = Annotated[OrgContext, Depends(org_context)]


async def org_session(
    ctx: CurrentOrg,
    sessions: Annotated[async_sessionmaker[AsyncSession], Depends(get_sessionmaker)],
) -> AsyncIterator[AsyncSession]:
    async with tenant_session(sessions, ctx.org_id) as session:
        yield session


TenantSession = Annotated[AsyncSession, Depends(org_session)]
