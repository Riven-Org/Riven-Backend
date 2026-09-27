"""Cached JSON Web Key Set of the identity provider (S03.1.2).

Keys are fetched once and reused for `ttl_seconds`. A token signed with an unknown key id
forces a refresh (the IdP rotated its keys), at most once per `min_refresh_seconds` so a
flood of forged tokens cannot hammer the IdP.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from jwt import PyJWK

Fetch = Callable[[], Awaitable[dict[str, Any]]]


def http_fetcher(url: str, timeout: float = 5.0) -> Fetch:
    async def fetch() -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    return fetch


class JwksCache:
    def __init__(
        self, fetch: Fetch, *, ttl_seconds: float = 600, min_refresh_seconds: float = 30
    ) -> None:
        self._fetch = fetch
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_seconds
        self._keys: dict[str, PyJWK] = {}
        self._fetched_at = float("-inf")
        self._lock = asyncio.Lock()
        self.fetch_count = 0

    async def get(self, kid: str) -> PyJWK | None:
        now = time.monotonic()
        stale = now - self._fetched_at > self._ttl
        unknown = kid not in self._keys and now - self._fetched_at > self._min_refresh
        if stale or unknown:
            await self._refresh()
        return self._keys.get(kid)

    async def _refresh(self) -> None:
        async with self._lock:
            if time.monotonic() - self._fetched_at < self._min_refresh:
                return  # another request refreshed while we waited
            data = await self._fetch()
            self.fetch_count += 1
            self._keys = {
                k["kid"]: PyJWK.from_dict(k)
                for k in data.get("keys", [])
                if k.get("use", "sig") == "sig" and "kid" in k
            }
            self._fetched_at = time.monotonic()
