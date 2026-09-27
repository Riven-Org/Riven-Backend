"""S03.2.1: orgs, membership and invitations."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_db.models import Invitation

from api_fakes import ALICE, BOB, CAROL, FakeMailer, add_member, make_org  # isort: skip

Auth = Callable[..., dict[str, str]]


async def test_creator_becomes_owner_of_a_new_org(client: AsyncClient, auth: Auth) -> None:
    created = await client.post("/v1/orgs", json={"name": "Acme Inc"}, headers=auth(**ALICE))

    assert created.status_code == 201
    assert created.json()["role"] == "owner"
    assert created.json()["slug"] == "acme-inc"
    listed = await client.get("/v1/orgs", headers=auth(**ALICE))
    assert [o["id"] for o in listed.json()] == [created.json()["id"]]


async def test_invited_user_joins_the_org_with_the_assigned_role(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")

    invited = await client.post(
        f"/v1/orgs/{org}/invitations",
        json={"email": "Carol@Acme.dev", "role": "reviewer"},
        headers=auth(**ALICE),
    )
    assert invited.status_code == 201
    to, subject, body = mailer.sent[-1]
    assert to == "carol@acme.dev"
    assert "Acme" in subject and "/invite?token=" in body

    accepted = await client.post(
        "/v1/invitations/accept", json={"token": mailer.last_token()}, headers=auth(**CAROL)
    )

    assert accepted.status_code == 200
    assert accepted.json() == {**accepted.json(), "id": org, "role": "reviewer"}
    members = (await client.get(f"/v1/orgs/{org}/members", headers=auth(**CAROL))).json()
    assert {(m["email"], m["role"]) for m in members} == {
        ("alice@acme.dev", "owner"),
        ("carol@acme.dev", "reviewer"),
    }


async def test_invitation_cannot_be_used_by_another_email(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    await client.post(
        f"/v1/orgs/{org}/invitations", json={"email": "carol@acme.dev"}, headers=auth(**ALICE)
    )

    stolen = await client.post(
        "/v1/invitations/accept", json={"token": mailer.last_token()}, headers=auth(**BOB)
    )

    assert stolen.status_code == 403


async def test_invitation_works_once(client: AsyncClient, auth: Auth, mailer: FakeMailer) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    await add_member(client, mailer, org, auth(**ALICE), auth(**CAROL), CAROL["email"], "viewer")

    again = await client.post(
        "/v1/invitations/accept", json={"token": mailer.last_token()}, headers=auth(**CAROL)
    )

    assert again.status_code == 404


async def test_revoked_and_expired_invitations_are_rejected(
    client: AsyncClient,
    auth: Auth,
    mailer: FakeMailer,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    invited = await client.post(
        f"/v1/orgs/{org}/invitations", json={"email": "carol@acme.dev"}, headers=auth(**ALICE)
    )
    revoked_token = mailer.last_token()
    await client.delete(f"/v1/orgs/{org}/invitations/{invited.json()['id']}", headers=auth(**ALICE))
    await client.post(
        f"/v1/orgs/{org}/invitations", json={"email": "carol@acme.dev"}, headers=auth(**ALICE)
    )
    expired_token = mailer.last_token()
    async with sessions() as session, session.begin():
        await session.execute(
            update(Invitation)
            .where(Invitation.revoked_at.is_(None))
            .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        )

    for token in (revoked_token, expired_token):
        response = await client.post(
            "/v1/invitations/accept", json={"token": token}, headers=auth(**CAROL)
        )
        assert response.status_code == 404


async def test_only_owners_and_admins_invite(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    await add_member(client, mailer, org, auth(**ALICE), auth(**CAROL), CAROL["email"], "viewer")

    response = await client.post(
        f"/v1/orgs/{org}/invitations", json={"email": "x@acme.dev"}, headers=auth(**CAROL)
    )

    assert response.status_code == 403


async def test_inviting_an_existing_member_conflicts(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")

    response = await client.post(
        f"/v1/orgs/{org}/invitations", json={"email": "alice@acme.dev"}, headers=auth(**ALICE)
    )

    assert response.status_code == 409
