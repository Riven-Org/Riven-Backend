from fastapi import APIRouter
from pydantic import BaseModel

from riven_api.auth.access import PermissionedRoute
from riven_api.auth.deps import CurrentPrincipal

router = APIRouter(prefix="/v1", tags=["identity"], route_class=PermissionedRoute)


class MeOut(BaseModel):
    id: str
    kind: str
    email: str
    name: str
    producer_kind: str
    producer_identity: str


@router.get("/me")
async def me(principal: CurrentPrincipal) -> MeOut:
    """The authenticated caller."""
    return MeOut(
        id=str(principal.id),
        kind=principal.kind,
        email=principal.email,
        name=principal.name,
        producer_kind=principal.producer.kind.value,
        producer_identity=principal.producer.identity,
    )
