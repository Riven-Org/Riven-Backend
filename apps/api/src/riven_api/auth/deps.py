"""FastAPI dependencies that authenticate every request (S03.1, S03.4).

A bearer token is either an OIDC access token from Keycloak (a person) or an API key
`rvn_...` (a service account acting for an AI agent, CI system or bot).
"""

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.jwks import JwksCache, http_fetcher
from riven_api.auth.tokens import InvalidToken, TokenVerifier
from riven_api.config import get_settings
from riven_api.db import get_session
from riven_api.services import api_keys, sessions, users
from riven_schemas import Producer, ProducerKind

SERVICE_ACCOUNT_PRODUCERS = {
    "ai_agent": ProducerKind.AI_AGENT,
    "ci": ProducerKind.BOT,
    "bot": ProducerKind.BOT,
}


@dataclass(frozen=True)
class Principal:
    """Who is calling: a signed-in person or a service account bound to one org."""

    kind: Literal["user", "service_account"]
    id: UUID
    email: str
    name: str
    producer: Producer
    session_id: str | None = None
    subject: str = ""  # identity-provider user id (Keycloak `sub`)
    org_id: str | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)


@lru_cache
def get_token_verifier() -> TokenVerifier:
    settings = get_settings()
    return TokenVerifier(
        JwksCache(http_fetcher(settings.oidc_jwks_url)),
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("missing bearer token")
    return token.strip()


async def _service_account(session: AsyncSession, token: str) -> Principal:
    try:
        found = await api_keys.authenticate(session, token)
    except api_keys.InvalidKey as exc:
        raise _unauthorized(f"invalid api key: {exc}") from exc
    account = found.account
    return Principal(
        kind="service_account",
        id=account.id,
        email="",
        name=account.name,
        producer=Producer(
            kind=SERVICE_ACCOUNT_PRODUCERS.get(account.kind, ProducerKind.UNKNOWN),
            identity=f"sa:{account.name}",
            agent_model=account.agent_model,
        ),
        org_id=account.org_id,
        scopes=frozenset(found.key.scopes),
    )


async def current_principal(
    token: Annotated[str, Depends(bearer_token)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Principal:
    if api_keys.looks_like_api_key(token):
        return await _service_account(session, token)
    try:
        claims = await verifier.verify(token)
    except InvalidToken as exc:
        raise _unauthorized(f"invalid token: {exc}") from exc
    if not claims.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="email_not_verified")
    if claims.session_id and await sessions.is_revoked(session, claims.session_id):
        raise _unauthorized("session revoked")
    user = await users.get_or_provision(session, claims)
    await session.commit()
    return Principal(
        kind="user",
        id=user.id,
        email=user.email,
        name=user.name,
        producer=Producer(kind=ProducerKind.HUMAN, identity=user.email),
        session_id=claims.session_id,
        subject=claims.subject,
    )


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


async def current_user(principal: CurrentPrincipal) -> Principal:
    """Endpoints only a person may call (creating orgs, accepting invitations, …)."""
    if principal.kind != "user":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="users_only")
    return principal


CurrentUser = Annotated[Principal, Depends(current_user)]
