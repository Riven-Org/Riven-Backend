"""Keycloak admin calls the API makes for its users (S03.5): MFA status, forcing enrolment,
listing and ending sessions. Uses the confidential `riven-api` client's service account
(client credentials), whose realm roles allow viewing and managing users."""

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Protocol

import httpx

from riven_api.config import get_settings

MFA_CREDENTIALS = {"otp", "webauthn", "webauthn-passwordless"}


@dataclass(frozen=True)
class IdpSession:
    id: str
    ip_address: str
    started_at: datetime
    last_access_at: datetime
    clients: list[str]


class IdpAdmin(Protocol):
    async def has_mfa(self, user_id: str) -> bool: ...

    async def require_mfa_enrolment(self, user_id: str) -> None: ...

    async def sessions(self, user_id: str) -> list[IdpSession]: ...

    async def end_session(self, session_id: str) -> None: ...


def _when(millis: int) -> datetime:
    return datetime.fromtimestamp(millis / 1000, UTC)


class KeycloakAdmin:
    def __init__(self, base_url: str, realm: str, client_id: str, client_secret: str) -> None:
        self._base = base_url.rstrip("/")
        self._realm = realm
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: tuple[str, float] | None = None
        self._mfa_cache: dict[str, tuple[bool, float]] = {}

    async def _auth(self, client: httpx.AsyncClient) -> dict[str, str]:
        if self._token is None or self._token[1] < time.monotonic():
            response = await client.post(
                f"{self._base}/realms/{self._realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
            body = response.json()
            self._token = (body["access_token"], time.monotonic() + body["expires_in"] - 30)
        return {"Authorization": f"Bearer {self._token[0]}"}

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.request(
                method,
                f"{self._base}/admin/realms/{self._realm}{path}",
                headers=await self._auth(client),
                **kwargs,
            )
            response.raise_for_status()
            return response.json() if response.content else None

    async def has_mfa(self, user_id: str) -> bool:
        cached = self._mfa_cache.get(user_id)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        credentials = await self._request("GET", f"/users/{user_id}/credentials")
        enrolled = any(c.get("type") in MFA_CREDENTIALS for c in credentials)
        # Only cache "enrolled": a user who just set up 2FA must get in right away.
        if enrolled:
            self._mfa_cache[user_id] = (True, time.monotonic() + 60)
        return enrolled

    async def require_mfa_enrolment(self, user_id: str) -> None:
        user = await self._request("GET", f"/users/{user_id}")
        actions = set(user.get("requiredActions", []))
        if "CONFIGURE_TOTP" not in actions:
            await self._request(
                "PUT",
                f"/users/{user_id}",
                json={"requiredActions": sorted(actions | {"CONFIGURE_TOTP"})},
            )

    async def sessions(self, user_id: str) -> list[IdpSession]:
        rows = await self._request("GET", f"/users/{user_id}/sessions")
        return [
            IdpSession(
                id=row["id"],
                ip_address=row.get("ipAddress", ""),
                started_at=_when(row["start"]),
                last_access_at=_when(row["lastAccess"]),
                clients=sorted(row.get("clients", {}).values()),
            )
            for row in rows
        ]

    async def end_session(self, session_id: str) -> None:
        await self._request("DELETE", f"/sessions/{session_id}")


@lru_cache
def get_idp_admin() -> IdpAdmin:
    s = get_settings()
    return KeycloakAdmin(
        s.keycloak_admin_url or s.oidc_issuer.split("/realms/")[0],
        s.oidc_issuer.rsplit("/", 1)[-1],
        s.keycloak_admin_client_id,
        s.keycloak_admin_client_secret.get_secret_value(),
    )
