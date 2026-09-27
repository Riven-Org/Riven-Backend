"""S03.3: permission matrix documented, every endpoint declares its permission (deny by
default), and the API enforces it for every role."""

import re
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from httpx import AsyncClient

from riven_api.auth.access import PermissionedRoute, UndeclaredAccess
from riven_api.auth.org import CurrentOrg
from riven_api.auth.permissions import MATRIX, Permission, render
from riven_api.main import create_app
from riven_schemas import Role

from api_fakes import ALICE, CAROL, FakeMailer, add_member, make_org  # isort: skip

Auth = Callable[..., dict[str, str]]
PARAM = re.compile(r"{(\w+)}")
DOC = Path(__file__).resolve().parents[3] / "docs" / "permissions.md"


# --- the matrix ------------------------------------------------------------------------


def test_permission_matrix_doc_is_up_to_date() -> None:
    assert DOC.read_text() == render(), (
        "docs/permissions.md is stale: "
        "uv run python -m riven_api.auth.permissions > docs/permissions.md"
    )


def test_roles_are_nested_from_viewer_to_owner() -> None:
    ladder = [Role.VIEWER, Role.REVIEWER, Role.MAINTAINER, Role.ADMIN, Role.OWNER]
    for lower, higher in zip(ladder, ladder[1:], strict=False):
        assert MATRIX[lower] < MATRIX[higher], f"{higher} must include everything {lower} has"
    assert MATRIX[Role.OWNER] == frozenset(Permission)


def test_viewers_can_only_read() -> None:
    assert all(p.value.endswith(".read") for p in MATRIX[Role.VIEWER])


def test_matrix_covers_confirm_bug_approve_review_and_create_lock() -> None:
    assert Permission.BUGS_CONFIRM in MATRIX[Role.REVIEWER]
    assert Permission.REVIEWS_APPROVE in MATRIX[Role.REVIEWER]
    assert Permission.LOCKS_CREATE in MATRIX[Role.MAINTAINER]
    assert Permission.LOCKS_CREATE not in MATRIX[Role.REVIEWER]


# --- deny by default -------------------------------------------------------------------


def test_every_v1_endpoint_declares_its_access() -> None:
    schema = create_app().openapi()

    undeclared = [
        f"{method.upper()} {path}"
        for path, operations in schema["paths"].items()
        if path.startswith("/v1")
        for method, operation in operations.items()
        if not operation.get("x-riven-permission")
    ]

    assert undeclared == []


def test_org_endpoint_without_a_permission_is_refused_at_startup() -> None:
    router = APIRouter(route_class=PermissionedRoute)

    with pytest.raises(UndeclaredAccess, match="/v1/orgs/{org_id}/danger"):

        @router.post("/v1/orgs/{org_id}/danger")
        async def danger(ctx: CurrentOrg) -> None: ...


def test_unauthenticated_endpoint_must_be_marked_public() -> None:
    router = APIRouter(route_class=PermissionedRoute)

    with pytest.raises(UndeclaredAccess):

        @router.get("/v1/open")
        async def open_endpoint() -> None: ...

    @router.get("/v1/status", openapi_extra={"x-riven-public": True})
    async def status_endpoint() -> None: ...


# --- enforcement for every role ----------------------------------------------------------


@pytest.fixture
async def org_with_every_role(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> tuple[str, dict[Role, dict[str, str]]]:
    owner = auth(**ALICE)
    org = await make_org(client, owner, "Acme")
    headers = {Role.OWNER: owner}
    for role in (Role.ADMIN, Role.MAINTAINER, Role.REVIEWER, Role.VIEWER):
        who = {"sub": f"user-{role.value}", "email": f"{role.value}@acme.dev", "name": role.value}
        await add_member(client, mailer, org, owner, auth(**who), who["email"], role.value)
        headers[role] = auth(**who)
    return org, headers


async def test_every_endpoint_refuses_roles_without_its_permission(
    app: FastAPI, client: AsyncClient, org_with_every_role: tuple[str, dict[Role, dict[str, str]]]
) -> None:
    org, headers = org_with_every_role
    checked, wrong = 0, []
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            required = operation.get("x-riven-permission", "")
            if "{org_id}" not in path or "." not in required:
                continue
            needed = {Permission(p) for p in required.split(",")}
            url = path.format(
                **{p: str(uuid.uuid4()) for p in PARAM.findall(path)} | {"org_id": org}
            )
            for role, header in headers.items():
                if needed <= MATRIX[role]:
                    continue
                checked += 1
                response = await client.request(method.upper(), url, headers=header, json={})
                if response.status_code != 403:
                    wrong.append(f"{role} {method.upper()} {path} -> {response.status_code}")

    assert checked > 10
    assert wrong == []


async def test_org_response_lists_the_callers_permissions(
    client: AsyncClient, org_with_every_role: tuple[str, dict[Role, dict[str, str]]]
) -> None:
    org, headers = org_with_every_role

    viewer = (await client.get(f"/v1/orgs/{org}", headers=headers[Role.VIEWER])).json()

    assert viewer["role"] == "viewer"
    assert set(viewer["permissions"]) == {p.value for p in MATRIX[Role.VIEWER]}


# --- role management rules --------------------------------------------------------------


async def _member_id(client: AsyncClient, org: str, header: dict[str, str], email: str) -> str:
    members = (await client.get(f"/v1/orgs/{org}/members", headers=header)).json()
    return next(m["user_id"] for m in members if m["email"] == email)


async def test_admin_changes_roles_but_cannot_create_owners(
    client: AsyncClient, org_with_every_role: tuple[str, dict[Role, dict[str, str]]]
) -> None:
    org, headers = org_with_every_role
    viewer = await _member_id(client, org, headers[Role.ADMIN], "viewer@acme.dev")

    promoted = await client.patch(
        f"/v1/orgs/{org}/members/{viewer}", json={"role": "maintainer"}, headers=headers[Role.ADMIN]
    )
    to_owner = await client.patch(
        f"/v1/orgs/{org}/members/{viewer}", json={"role": "owner"}, headers=headers[Role.ADMIN]
    )

    assert promoted.status_code == 200 and promoted.json()["role"] == "maintainer"
    assert to_owner.status_code == 403


async def test_the_last_owner_cannot_be_demoted_or_removed(
    client: AsyncClient, org_with_every_role: tuple[str, dict[Role, dict[str, str]]]
) -> None:
    org, headers = org_with_every_role
    owner = await _member_id(client, org, headers[Role.OWNER], "alice@acme.dev")

    demote = await client.patch(
        f"/v1/orgs/{org}/members/{owner}", json={"role": "admin"}, headers=headers[Role.OWNER]
    )
    remove = await client.delete(f"/v1/orgs/{org}/members/{owner}", headers=headers[Role.OWNER])

    assert demote.status_code == remove.status_code == 409


async def test_removed_member_loses_access(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    await add_member(client, mailer, org, auth(**ALICE), auth(**CAROL), CAROL["email"], "viewer")
    carol = await _member_id(client, org, auth(**ALICE), CAROL["email"])

    removed = await client.delete(f"/v1/orgs/{org}/members/{carol}", headers=auth(**ALICE))

    assert removed.status_code == 204
    assert (await client.get(f"/v1/orgs/{org}", headers=auth(**CAROL))).status_code == 404


async def test_owner_renames_the_org(client: AsyncClient, auth: Auth) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")

    renamed = await client.patch(
        f"/v1/orgs/{org}", json={"name": "Acme Labs"}, headers=auth(**ALICE)
    )

    assert renamed.json()["name"] == "Acme Labs"
