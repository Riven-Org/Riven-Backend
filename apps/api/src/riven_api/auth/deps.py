"""FastAPI dependencies that authenticate every request (S03.1)."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from riven_api.auth.jwks import JwksCache, http_fetcher
from riven_api.auth.tokens import InvalidToken, TokenVerifier
from riven_api.config import get_settings
from riven_api.db import get_session
from riven_api.services import users


@dataclass(frozen=True)
class Principal:
    """Who is calling: a signed-in person (S03.1) or a service account (S03.4)."""

    kind: Literal["user", "service_account"]
    id: UUID
    email: str
    name: str
    session_id: str | None = None


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


async def current_principal(
    token: Annotated[str, Depends(bearer_token)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Principal:
    try:
        claims = await verifier.verify(token)
    except InvalidToken as exc:
        raise _unauthorized(f"invalid token: {exc}") from exc
    if not claims.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="email_not_verified")
    user = await users.get_or_provision(session, claims)
    await session.commit()
    return Principal(
        kind="user", id=user.id, email=user.email, name=user.name, session_id=claims.session_id
    )


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
