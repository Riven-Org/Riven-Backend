"""Test doubles shared by the API tests."""

import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://idp.test/realms/riven"
AUDIENCE = "riven-api"


class FakeIdP:
    """Signs tokens like Keycloak and serves its JWKS; can rotate keys."""

    def __init__(self) -> None:
        self.fetches = 0
        self.rotate()

    def rotate(self) -> None:
        self.kid = uuid.uuid4().hex
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    async def jwks(self) -> dict[str, Any]:
        self.fetches += 1
        public = RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {"keys": [{**public, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def token(self, **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": AUDIENCE,
            "sub": "user-alice",
            "typ": "Bearer",
            "iat": now,
            "exp": now + 300,
            "email": "alice@acme.dev",
            "email_verified": True,
            "name": "Alice",
            "sid": "session-1",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.private_key, algorithm="RS256", headers={"kid": self.kid})
