"""S03.4: scoped, rotatable API keys for agents/CI, hashed at rest and shown once; changes
record the authenticated producer."""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_db.models import ApiKey, Change
from riven_events import OutboxEvent

from api_fakes import ALICE, BOB, FakeMailer, add_member, make_org  # isort: skip

Auth = Callable[..., dict[str, str]]
CHANGE = {"repository": "acme/shop", "commit_sha": "a1b2c3d4", "files_changed": ["auth.py"]}


def bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def agent_key(
    client: AsyncClient, org: str, owner: dict[str, str], **key: Any
) -> dict[str, Any]:
    account = await client.post(
        f"/v1/orgs/{org}/service-accounts",
        json={"name": "claude-code", "kind": "ai_agent", "agent_model": "claude-opus"},
        headers=owner,
    )
    assert account.status_code == 201, account.text
    issued = await client.post(
        f"/v1/orgs/{org}/service-accounts/{account.json()['id']}/keys", json=key, headers=owner
    )
    assert issued.status_code == 201, issued.text
    body: dict[str, Any] = issued.json()
    return body


@pytest.fixture
async def org(client: AsyncClient, auth: Auth) -> str:
    return await make_org(client, auth(**ALICE), "Acme")


async def test_key_is_shown_once_and_only_its_hash_is_stored(
    client: AsyncClient, auth: Auth, org: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    issued = await agent_key(client, org, auth(**ALICE))
    secret = issued["secret"]

    listed = (await client.get(f"/v1/orgs/{org}/service-accounts", headers=auth(**ALICE))).json()

    assert secret.startswith(issued["prefix"] + "_")
    assert "secret" not in listed[0]["keys"][0]
    assert secret not in str(listed)
    async with sessions() as session:
        stored = await session.scalar(select(ApiKey))
    assert stored is not None
    assert stored.secret_hash.startswith("$argon2")
    assert secret.split("_", 2)[2] not in stored.secret_hash


async def test_agent_key_authenticates_as_the_service_account(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    secret = (await agent_key(client, org, auth(**ALICE)))["secret"]

    me = await client.get("/v1/me", headers=bearer(secret))

    assert me.json()["kind"] == "service_account"
    assert me.json()["producer_kind"] == "ai_agent"


async def test_change_from_an_agent_key_records_the_agent_as_producer(
    client: AsyncClient, auth: Auth, org: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    secret = (await agent_key(client, org, auth(**ALICE)))["secret"]

    submitted = await client.post(f"/v1/orgs/{org}/changes", json=CHANGE, headers=bearer(secret))

    assert submitted.status_code == 201, submitted.text
    detail = await client.get(
        f"/v1/orgs/{org}/changes/{submitted.json()['id']}", headers=auth(**ALICE)
    )
    assert detail.json()["producer"] == {
        "kind": "ai_agent",
        "identity": "sa:claude-code",
        "agent_model": "claude-opus",
    }
    async with sessions() as session:
        event = await session.scalar(select(OutboxEvent))
    assert event is not None and event.event_type == "change.captured"
    assert event.payload["producer"]["kind"] == "ai_agent"


async def test_change_from_a_person_records_them_as_human_producer(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    submitted = await client.post(f"/v1/orgs/{org}/changes", json=CHANGE, headers=auth(**ALICE))

    assert submitted.json()["producer"] == {
        "kind": "human",
        "identity": "alice@acme.dev",
        "agent_model": None,
    }


async def test_producer_cannot_be_claimed_in_the_request_body(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    secret = (await agent_key(client, org, auth(**ALICE)))["secret"]
    spoofed = {**CHANGE, "producer": {"kind": "human", "identity": "alice@acme.dev"}}

    response = await client.post(f"/v1/orgs/{org}/changes", json=spoofed, headers=bearer(secret))

    assert response.status_code == 422


async def test_resubmitting_a_commit_returns_the_existing_change(
    client: AsyncClient, auth: Auth, org: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    first = await client.post(f"/v1/orgs/{org}/changes", json=CHANGE, headers=auth(**ALICE))
    again = await client.post(f"/v1/orgs/{org}/changes", json=CHANGE, headers=auth(**ALICE))

    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    async with sessions() as session:
        assert len(list(await session.scalars(select(Change)))) == 1


async def test_key_can_only_do_what_its_scopes_allow(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    read_only = (await agent_key(client, org, auth(**ALICE), scopes=["changes.read"]))["secret"]

    submit = await client.post(f"/v1/orgs/{org}/changes", json=CHANGE, headers=bearer(read_only))
    read = await client.get(f"/v1/orgs/{org}/changes", headers=bearer(read_only))
    members = await client.get(f"/v1/orgs/{org}/members", headers=bearer(read_only))

    assert submit.status_code == 403
    assert read.status_code == 200
    assert members.status_code == 403


async def test_keys_cannot_carry_permissions_their_creator_lacks(
    client: AsyncClient, auth: Auth, org: str, mailer: FakeMailer
) -> None:
    admin = {"sub": "user-admin", "email": "admin@acme.dev", "name": "Admin"}
    await add_member(client, mailer, org, auth(**ALICE), auth(**admin), admin["email"], "admin")

    account = await client.post(
        f"/v1/orgs/{org}/service-accounts", json={"name": "ci", "kind": "ci"}, headers=auth(**admin)
    )
    response = await client.post(
        f"/v1/orgs/{org}/service-accounts/{account.json()['id']}/keys",
        json={"scopes": ["org.delete"]},
        headers=auth(**admin),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "cannot_grant:org.delete"


async def test_revoked_key_is_rejected_on_its_next_use(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    issued = await agent_key(client, org, auth(**ALICE))
    assert (await client.get("/v1/me", headers=bearer(issued["secret"]))).status_code == 200

    await client.delete(f"/v1/orgs/{org}/api-keys/{issued['id']}", headers=auth(**ALICE))
    revoked_at = time.monotonic()
    response = await client.get("/v1/me", headers=bearer(issued["secret"]))

    assert response.status_code == 401
    assert "revoked" in response.json()["detail"]
    assert time.monotonic() - revoked_at < 60


async def test_expired_key_is_rejected(
    client: AsyncClient, auth: Auth, org: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    issued = await agent_key(client, org, auth(**ALICE), expires_in_days=1)
    async with sessions() as session, session.begin():
        await session.execute(
            update(ApiKey).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

    response = await client.get("/v1/me", headers=bearer(issued["secret"]))

    assert response.status_code == 401
    assert "expired" in response.json()["detail"]


async def test_rotation_replaces_the_secret(client: AsyncClient, auth: Auth, org: str) -> None:
    old = await agent_key(client, org, auth(**ALICE), scopes=["changes.read", "runs.read"])

    new = await client.post(f"/v1/orgs/{org}/api-keys/{old['id']}/rotate", headers=auth(**ALICE))

    assert new.status_code == 201
    assert new.json()["scopes"] == ["changes.read", "runs.read"]
    assert (await client.get("/v1/me", headers=bearer(old["secret"]))).status_code == 401
    assert (await client.get("/v1/me", headers=bearer(new.json()["secret"]))).status_code == 200


async def test_disabling_an_account_revokes_its_keys(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    issued = await agent_key(client, org, auth(**ALICE))
    listed = await client.get(f"/v1/orgs/{org}/service-accounts", headers=auth(**ALICE))
    account_id = listed.json()[0]["id"]

    await client.delete(f"/v1/orgs/{org}/service-accounts/{account_id}", headers=auth(**ALICE))

    assert (await client.get("/v1/me", headers=bearer(issued["secret"]))).status_code == 401


async def test_last_use_is_recorded(
    client: AsyncClient, auth: Auth, org: str, sessions: async_sessionmaker[AsyncSession]
) -> None:
    issued = await agent_key(client, org, auth(**ALICE))

    await client.get("/v1/me", headers=bearer(issued["secret"]))

    async with sessions() as session:
        key = await session.scalar(select(ApiKey))
    assert key is not None and key.last_used_at is not None


async def test_a_key_only_reaches_its_own_org(client: AsyncClient, auth: Auth, org: str) -> None:
    other = await make_org(client, auth(**BOB), "Globex")
    secret = (await agent_key(client, org, auth(**ALICE)))["secret"]

    response = await client.get(f"/v1/orgs/{other}/changes", headers=bearer(secret))

    assert response.status_code == 404


async def test_service_accounts_cannot_use_person_only_endpoints(
    client: AsyncClient, auth: Auth, org: str
) -> None:
    secret = (await agent_key(client, org, auth(**ALICE)))["secret"]

    response = await client.post("/v1/orgs", json={"name": "Rogue"}, headers=bearer(secret))

    assert response.status_code == 403


@pytest.mark.parametrize("token", ["rvn_", "rvn_abc", "rvn_deadbeef0000_wrong-secret"])
async def test_malformed_or_unknown_keys_get_401(client: AsyncClient, token: str) -> None:
    assert (await client.get("/v1/me", headers=bearer(token))).status_code == 401
