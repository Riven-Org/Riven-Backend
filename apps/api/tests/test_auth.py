"""S03.1: users sign in through the IdP; the API validates the JWT on every request."""

import time
from collections.abc import Callable

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_api.auth.jwks import JwksCache
from riven_api.auth.tokens import InvalidToken, TokenVerifier
from riven_db.models import User

from api_fakes import AUDIENCE, ISSUER, FakeIdP  # isort: skip

# --- token verification (no database) ----------------------------------------------------


async def test_valid_token_yields_its_claims(idp: FakeIdP, verifier: TokenVerifier) -> None:
    claims = await verifier.verify(idp.token())

    assert claims.subject == "user-alice"
    assert claims.email_verified is True
    assert claims.session_id == "session-1"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"exp": int(time.time()) - 120}, "expired"),
        ({"iss": "https://evil.test/realms/riven"}, "issuer"),
        ({"aud": "some-other-api"}, "(?i)audience"),
        ({"typ": "ID"}, "not an access token"),
        ({"sub": None}, "sub"),
    ],
)
async def test_invalid_tokens_are_rejected(
    idp: FakeIdP, verifier: TokenVerifier, overrides: dict[str, object], reason: str
) -> None:
    with pytest.raises(InvalidToken, match=reason):
        await verifier.verify(idp.token(**overrides))


async def test_token_signed_by_another_key_is_rejected(verifier: TokenVerifier) -> None:
    forger = FakeIdP()  # same claims, attacker's key and kid

    with pytest.raises(InvalidToken, match="unknown signing key"):
        await verifier.verify(forger.token())


async def test_tampered_token_is_rejected(idp: FakeIdP, verifier: TokenVerifier) -> None:
    header, payload, signature = idp.token().split(".")
    other_payload = idp.token(sub="mallory").split(".")[1]

    with pytest.raises(InvalidToken):
        await verifier.verify(f"{header}.{other_payload}.{signature[::-1]}")
    with pytest.raises(InvalidToken, match="malformed"):
        await verifier.verify("not-a-jwt")


async def test_signing_keys_are_cached_between_requests(
    idp: FakeIdP, verifier: TokenVerifier
) -> None:
    for _ in range(5):
        await verifier.verify(idp.token())

    assert idp.fetches == 1


async def test_rotated_signing_key_is_picked_up(idp: FakeIdP) -> None:
    verifier = TokenVerifier(
        JwksCache(idp.jwks, min_refresh_seconds=0), issuer=ISSUER, audience=AUDIENCE
    )
    await verifier.verify(idp.token())

    idp.rotate()

    assert (await verifier.verify(idp.token())).subject == "user-alice"
    assert idp.fetches == 2


# --- the API (needs the test database) -----------------------------------------------------


async def test_every_api_request_without_a_token_gets_401(client: AsyncClient) -> None:
    response = await client.get("/v1/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_expired_token_gets_401(client: AsyncClient, idp: FakeIdP) -> None:
    token = idp.token(exp=int(time.time()) - 120)

    response = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_unverified_email_account_is_refused(
    client: AsyncClient, auth: Callable[..., dict[str, str]]
) -> None:
    response = await client.get("/v1/me", headers=auth(email_verified=False))

    assert response.status_code == 403
    assert response.json()["detail"] == "email_not_verified"


async def test_first_sign_in_provisions_the_user_once(
    client: AsyncClient,
    auth: Callable[..., dict[str, str]],
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await client.get("/v1/me", headers=auth())
    again = await client.get("/v1/me", headers=auth(name="Alice Liddell"))

    assert first.status_code == 200
    assert first.json()["email"] == "alice@acme.dev"
    assert again.json()["id"] == first.json()["id"]
    assert again.json()["name"] == "Alice Liddell"
    async with sessions() as session:
        assert await session.scalar(select(func.count()).select_from(User)) == 1


async def test_social_login_users_are_accepted(
    client: AsyncClient, auth: Callable[..., dict[str, str]]
) -> None:
    """GitHub/Google accounts arrive with the IdP-trusted email marked verified."""
    response = await client.get("/v1/me", headers=auth(sub="github-123", email="octo@github.test"))

    assert response.status_code == 200
