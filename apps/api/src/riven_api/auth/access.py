"""Deny-by-default access declarations (S03.3.2).

Every `/v1` endpoint must declare its access, or the app refuses to start:

- `Depends(require(Permission.X))` — org endpoints; the caller's role (or API key scopes)
  must grant X;
- `Depends(current_principal)` without an org — endpoints about the caller themselves
  ("authenticated");
- `public=True` via `openapi_extra={"x-riven-public": True}` — no authentication at all.

`PermissionedRoute` records the declaration in the OpenAPI schema as `x-riven-permission`.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

from riven_api.auth.deps import current_principal
from riven_api.auth.org import CurrentOrg, OrgContext, org_context
from riven_api.auth.permissions import Permission

PERMISSION_ATTR = "riven_permission"
AUTHENTICATED = "authenticated"
PUBLIC = "public"


class UndeclaredAccess(RuntimeError):
    pass


def require(permission: Permission) -> Callable[[OrgContext], Awaitable[OrgContext]]:
    async def check(ctx: CurrentOrg) -> OrgContext:
        if not ctx.can(permission):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"missing:{permission.value}")
        return ctx

    setattr(check, PERMISSION_ATTR, permission.value)
    check.__name__ = f"require_{permission.name.lower()}"
    return check


def Requires(permission: Permission) -> Any:  # noqa: N802  (reads like a type in signatures)
    """`ctx: Annotated[OrgContext, Requires(Permission.X)]`."""
    return Depends(require(permission))


def _calls(dependant: Dependant) -> list[Any]:
    found = []
    for sub in dependant.dependencies:
        found.append(sub.call)
        found.extend(_calls(sub))
    return found


def declared_access(dependant: Dependant, openapi_extra: dict[str, Any] | None) -> str | None:
    calls = _calls(dependant)
    declared = {getattr(c, PERMISSION_ATTR) for c in calls if hasattr(c, PERMISSION_ATTR)}
    permissions = sorted(declared)
    if permissions:
        return ",".join(permissions)
    if org_context in calls:
        return None  # an org endpoint must name its permission
    if current_principal in calls:
        return AUTHENTICATED
    if (openapi_extra or {}).get("x-riven-public"):
        return PUBLIC
    return None


class PermissionedRoute(APIRoute):
    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        super().__init__(path, endpoint, **kwargs)
        if not path.startswith("/v1"):
            return
        access = declared_access(self.dependant, self.openapi_extra)
        if access is None:
            raise UndeclaredAccess(
                f"{sorted(self.methods or ())} {path} declares no access: add "
                "Depends(require(Permission.…)), depend on current_principal, or mark it public"
            )
        self.openapi_extra = {**(self.openapi_extra or {}), "x-riven-permission": access}
