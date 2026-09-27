from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.access import PermissionedRoute
from riven_api.auth.deps import CurrentPrincipal, CurrentUser
from riven_api.db import get_session
from riven_api.services import sessions
from riven_api.services.idp_admin import IdpAdmin, get_idp_admin

router = APIRouter(prefix="/v1", tags=["identity"], route_class=PermissionedRoute)
Idp = Annotated[IdpAdmin, Depends(get_idp_admin)]
Session = Annotated[AsyncSession, Depends(get_session)]


class MeOut(BaseModel):
    id: str
    kind: str
    email: str
    name: str
    producer_kind: str
    producer_identity: str


class SecurityOut(BaseModel):
    mfa_enrolled: bool


class SessionOut(BaseModel):
    id: str
    ip_address: str
    started_at: datetime
    last_access_at: datetime
    clients: list[str]
    current: bool


class RevokedOut(BaseModel):
    revoked: int


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


@router.get("/me/security")
async def my_security(user: CurrentUser, idp: Idp) -> SecurityOut:
    """Whether the caller has a second factor (TOTP or security key) enrolled."""
    return SecurityOut(mfa_enrolled=await idp.has_mfa(user.subject))


@router.get("/me/sessions")
async def my_sessions(user: CurrentUser, idp: Idp) -> list[SessionOut]:
    """The caller's active sign-in sessions, newest activity first."""
    found = await idp.sessions(user.subject)
    return [
        SessionOut(**vars(s), current=s.id == user.session_id)
        for s in sorted(found, key=lambda s: s.last_access_at, reverse=True)
    ]


async def _end(session: AsyncSession, idp: IdpAdmin, user_id: UUID, session_id: str) -> None:
    await idp.end_session(session_id)
    await sessions.remember_revoked(session, session_id, user_id)


@router.delete("/me/sessions/{session_id}", status_code=204)
async def revoke_session(session_id: str, user: CurrentUser, idp: Idp, db: Session) -> Response:
    """End one of the caller's sessions; its tokens are refused from the next request on."""
    if session_id not in {s.id for s in await idp.sessions(user.subject)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")
    await _end(db, idp, user.id, session_id)
    await db.commit()
    return Response(status_code=204)


@router.post("/me/sessions/revoke-others")
async def revoke_other_sessions(user: CurrentUser, idp: Idp, db: Session) -> RevokedOut:
    """Sign out everywhere except this session."""
    others = [s.id for s in await idp.sessions(user.subject) if s.id != user.session_id]
    for session_id in others:
        await _end(db, idp, user.id, session_id)
    await db.commit()
    return RevokedOut(revoked=len(others))
