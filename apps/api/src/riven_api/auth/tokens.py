"""Access-token validation (S03.1.2): signature, expiry, issuer, audience, token type."""

from dataclasses import dataclass
from typing import Any

import jwt

from riven_api.auth.jwks import JwksCache

ALGORITHMS = ["RS256", "ES256", "PS256"]


class InvalidToken(Exception):
    """The bearer token must be rejected with 401."""


@dataclass(frozen=True)
class TokenClaims:
    subject: str
    email: str
    email_verified: bool
    name: str
    session_id: str | None
    raw: dict[str, Any]


class TokenVerifier:
    def __init__(self, jwks: JwksCache, *, issuer: str, audience: str, leeway: int = 30) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience
        self._leeway = leeway

    async def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidToken("malformed token") from exc
        if header.get("alg") not in ALGORITHMS:
            raise InvalidToken("unsupported algorithm")
        key = await self._jwks.get(str(header.get("kid", "")))
        if key is None:
            raise InvalidToken("unknown signing key")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise InvalidToken(str(exc)) from exc
        if claims.get("typ", "Bearer") != "Bearer":
            raise InvalidToken("not an access token")
        return TokenClaims(
            subject=str(claims["sub"]),
            email=str(claims.get("email", "")),
            email_verified=bool(claims.get("email_verified", False)),
            name=str(claims.get("name") or claims.get("preferred_username") or ""),
            session_id=claims.get("sid"),
            raw=claims,
        )
