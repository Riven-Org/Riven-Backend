"""S03.2.4: every org endpoint refuses callers from another org (404/403).

The routes are discovered from the app, so an endpoint added later is attacked automatically.
Path parameters are filled with real ids of the victim org's resources where they exist.
"""

import re
import uuid
from collections.abc import Callable

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_db.models import Repository

from api_fakes import ALICE, BOB, FakeMailer, make_org  # isort: skip

Auth = Callable[..., dict[str, str]]
PARAM = re.compile(r"{(\w+)}")


def org_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every (method, path) under /orgs/{org_id}, from the app's OpenAPI schema."""
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if "{org_id}" in path
        for method in operations
    )


async def _victim_resources(
    client: AsyncClient, auth: Auth, sessions: async_sessionmaker[AsyncSession], victim_org: str
) -> dict[str, str]:
    invited = await client.post(
        f"/v1/orgs/{victim_org}/invitations",
        json={"email": "someone@globex.dev"},
        headers=auth(**BOB),
    )
    async with sessions() as session, session.begin():
        repo = Repository(org_id=victim_org, full_name="globex/secret")
        session.add(repo)
        await session.flush()
        repo_id = str(repo.id)
    return {"invitation_id": invited.json()["id"], "repository_id": repo_id}


async def test_every_org_endpoint_denies_members_of_other_orgs(
    app: FastAPI,
    client: AsyncClient,
    auth: Auth,
    mailer: FakeMailer,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await make_org(client, auth(**ALICE), "Acme")
    victim = await make_org(client, auth(**BOB), "Globex")
    ids = await _victim_resources(client, auth, sessions, victim)
    routes = org_routes(app)
    assert len(routes) >= 6

    leaks = []
    for method, template in routes:
        params = {p: ids.get(p, str(uuid.uuid4())) for p in PARAM.findall(template)}
        path = template.format(**{**params, "org_id": victim})
        response = await client.request(method, path, headers=auth(**ALICE), json={})
        if response.status_code not in (403, 404):
            leaks.append(f"{method} {template} -> {response.status_code} {response.text[:120]}")

    assert leaks == [], "cross-tenant access:\n" + "\n".join(leaks)
    # The victim's data is untouched and still visible to its own members.
    pending = await client.get(f"/v1/orgs/{victim}/invitations", headers=auth(**BOB))
    assert [i["id"] for i in pending.json()] == [ids["invitation_id"]]
    repos = await client.get(f"/v1/orgs/{victim}/repositories", headers=auth(**BOB))
    assert [r["full_name"] for r in repos.json()] == ["globex/secret"]


async def test_unknown_org_looks_the_same_as_a_foreign_org(client: AsyncClient, auth: Auth) -> None:
    victim = await make_org(client, auth(**BOB), "Globex")

    foreign = await client.get(f"/v1/orgs/{victim}", headers=auth(**ALICE))
    missing = await client.get("/v1/orgs/org_doesnotexist", headers=auth(**ALICE))

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


async def test_own_org_domain_reads_only_return_own_rows(
    client: AsyncClient, auth: Auth, sessions: async_sessionmaker[AsyncSession]
) -> None:
    mine = await make_org(client, auth(**ALICE), "Acme")
    theirs = await make_org(client, auth(**BOB), "Globex")
    async with sessions() as session, session.begin():
        session.add_all(
            [
                Repository(org_id=mine, full_name="acme/shop"),
                Repository(org_id=theirs, full_name="globex/secret"),
            ]
        )

    repos = await client.get(f"/v1/orgs/{mine}/repositories", headers=auth(**ALICE))

    assert [r["full_name"] for r in repos.json()] == ["acme/shop"]
