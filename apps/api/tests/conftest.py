"""API test helpers: an in-memory identity provider that signs real RS256 tokens, and an app
wired to it and to the test database."""

from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_api.auth.deps import get_token_verifier
from riven_api.auth.jwks import JwksCache
from riven_api.auth.tokens import TokenVerifier
from riven_api.db import get_session
from riven_api.main import create_app

from api_fakes import AUDIENCE, ISSUER, FakeIdP  # noqa: F401  isort: skip


@pytest.fixture
def idp() -> FakeIdP:
    return FakeIdP()


@pytest.fixture
def verifier(idp: FakeIdP) -> TokenVerifier:
    return TokenVerifier(JwksCache(idp.jwks), issuer=ISSUER, audience=AUDIENCE)


@pytest.fixture
def app(verifier: TokenVerifier, sessions: async_sessionmaker[AsyncSession]) -> FastAPI:
    application = create_app()

    async def session() -> AsyncIterator[AsyncSession]:
        async with sessions() as s:
            yield s

    application.dependency_overrides[get_token_verifier] = lambda: verifier
    application.dependency_overrides[get_session] = session
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def auth(idp: FakeIdP) -> Callable[..., dict[str, str]]:
    """`auth(sub="u2", email=...)` → Authorization header for that user."""

    def headers(**claims: Any) -> dict[str, str]:
        return {"Authorization": f"Bearer {idp.token(**claims)}"}

    return headers
