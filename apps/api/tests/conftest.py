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
from riven_api.db import get_sessionmaker
from riven_api.main import create_app
from riven_api.services.idp_admin import get_idp_admin
from riven_api.services.mail import get_mailer

from api_fakes import AUDIENCE, ISSUER, FakeIdP, FakeIdpAdmin, FakeMailer  # isort: skip


@pytest.fixture
def idp() -> FakeIdP:
    return FakeIdP()


@pytest.fixture
def verifier(idp: FakeIdP) -> TokenVerifier:
    return TokenVerifier(JwksCache(idp.jwks), issuer=ISSUER, audience=AUDIENCE)


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


@pytest.fixture
def idp_admin() -> FakeIdpAdmin:
    return FakeIdpAdmin()


@pytest.fixture
def app(
    verifier: TokenVerifier,
    sessions: async_sessionmaker[AsyncSession],
    mailer: FakeMailer,
    idp_admin: FakeIdpAdmin,
) -> FastAPI:
    application = create_app()
    application.dependency_overrides[get_idp_admin] = lambda: idp_admin
    application.dependency_overrides[get_mailer] = lambda: mailer
    application.dependency_overrides[get_token_verifier] = lambda: verifier
    application.dependency_overrides[get_sessionmaker] = lambda: sessions
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
