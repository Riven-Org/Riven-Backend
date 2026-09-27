"""Test doubles shared by the API tests."""

import time
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
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


class FakeIdpAdmin:
    """Stands in for the Keycloak admin API."""

    def __init__(self) -> None:
        self.mfa: set[str] = set()
        self.forced_enrolment: set[str] = set()
        self.live: dict[str, list[str]] = {}
        self.ended: list[str] = []

    async def has_mfa(self, user_id: str) -> bool:
        return user_id in self.mfa

    async def require_mfa_enrolment(self, user_id: str) -> None:
        self.forced_enrolment.add(user_id)

    async def sessions(self, user_id: str) -> list[Any]:
        from datetime import UTC, datetime

        from riven_api.services.idp_admin import IdpSession

        now = datetime.now(UTC)
        return [
            IdpSession(
                id=sid,
                ip_address="127.0.0.1",
                started_at=now,
                last_access_at=now,
                clients=["riven-web"],
            )
            for sid in self.live.get(user_id, [])
        ]

    async def end_session(self, session_id: str) -> None:
        self.ended.append(session_id)
        for sids in self.live.values():
            if session_id in sids:
                sids.remove(session_id)


class FakeMailer:
    """Captures outgoing email instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))

    def last_token(self) -> str:
        body = self.sent[-1][2]
        return body.split("token=", 1)[1].split()[0]


ALICE = {"sub": "user-alice", "email": "alice@acme.dev", "name": "Alice"}
BOB = {"sub": "user-bob", "email": "bob@globex.dev", "name": "Bob"}
CAROL = {"sub": "user-carol", "email": "carol@acme.dev", "name": "Carol"}


async def make_org(client: AsyncClient, headers: dict[str, str], name: str) -> str:
    response = await client.post("/v1/orgs", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text
    org_id: str = response.json()["id"]
    return org_id


async def add_member(
    client: AsyncClient,
    mailer: FakeMailer,
    org_id: str,
    owner: dict[str, str],
    member: dict[str, str],
    email: str,
    role: str,
) -> None:
    invited = await client.post(
        f"/v1/orgs/{org_id}/invitations", json={"email": email, "role": role}, headers=owner
    )
    assert invited.status_code == 201, invited.text
    accepted = await client.post(
        "/v1/invitations/accept", json={"token": mailer.last_token()}, headers=member
    )
    assert accepted.status_code == 200, accepted.text
