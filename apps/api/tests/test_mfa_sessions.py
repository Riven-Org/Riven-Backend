"""S03.5: org-enforced MFA, session listing and revocation (Keycloak admin API faked)."""

from collections.abc import Callable

from httpx import AsyncClient

from api_fakes import ALICE, CAROL, FakeIdpAdmin, FakeMailer, add_member, make_org  # isort: skip

Auth = Callable[..., dict[str, str]]


async def test_org_admin_can_require_mfa_once_they_have_it(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")

    refused = await client.patch(
        f"/v1/orgs/{org}/security", json={"require_mfa": True}, headers=auth(**ALICE)
    )
    idp_admin.mfa.add(ALICE["sub"])
    enabled = await client.patch(
        f"/v1/orgs/{org}/security", json={"require_mfa": True}, headers=auth(**ALICE)
    )

    assert refused.status_code == 409 and refused.json()["detail"] == "enable_mfa_first"
    assert enabled.status_code == 200 and enabled.json()["require_mfa"] is True


async def test_member_without_mfa_is_forced_to_enrol(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    await add_member(client, mailer, org, auth(**ALICE), auth(**CAROL), CAROL["email"], "viewer")
    idp_admin.mfa.add(ALICE["sub"])
    policy = {"require_mfa": True}
    await client.patch(f"/v1/orgs/{org}/security", json=policy, headers=auth(**ALICE))

    blocked = await client.get(f"/v1/orgs/{org}", headers=auth(**CAROL))

    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "mfa_required"
    assert CAROL["sub"] in idp_admin.forced_enrolment  # Keycloak asks at next sign-in
    listed = (await client.get("/v1/orgs", headers=auth(**CAROL))).json()
    assert listed[0]["require_mfa"] is True  # the dashboard can explain why

    idp_admin.mfa.add(CAROL["sub"])
    assert (await client.get(f"/v1/orgs/{org}", headers=auth(**CAROL))).status_code == 200


async def test_orgs_without_the_policy_do_not_ask_for_mfa(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")

    assert (await client.get(f"/v1/orgs/{org}", headers=auth(**ALICE))).status_code == 200
    assert idp_admin.forced_enrolment == set()


async def test_viewer_cannot_change_the_security_policy(
    client: AsyncClient, auth: Auth, mailer: FakeMailer
) -> None:
    org = await make_org(client, auth(**ALICE), "Acme")
    await add_member(client, mailer, org, auth(**ALICE), auth(**CAROL), CAROL["email"], "viewer")

    response = await client.patch(
        f"/v1/orgs/{org}/security", json={"require_mfa": False}, headers=auth(**CAROL)
    )

    assert response.status_code == 403


async def test_security_status_reports_enrolment(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    before = (await client.get("/v1/me/security", headers=auth(**ALICE))).json()
    idp_admin.mfa.add(ALICE["sub"])
    after = (await client.get("/v1/me/security", headers=auth(**ALICE))).json()

    assert (before["mfa_enrolled"], after["mfa_enrolled"]) == (False, True)


async def test_user_lists_their_sessions_with_the_current_one_marked(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    idp_admin.live[ALICE["sub"]] = ["laptop", "phone"]

    listed = (await client.get("/v1/me/sessions", headers=auth(**ALICE, sid="laptop"))).json()

    assert {(s["id"], s["current"]) for s in listed} == {("laptop", True), ("phone", False)}


async def test_revoked_session_gets_401_on_its_next_call(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    idp_admin.live[ALICE["sub"]] = ["laptop", "phone"]
    phone = auth(**ALICE, sid="phone")
    assert (await client.get("/v1/me", headers=phone)).status_code == 200

    revoked = await client.delete("/v1/me/sessions/phone", headers=auth(**ALICE, sid="laptop"))
    next_call = await client.get("/v1/me", headers=phone)

    assert revoked.status_code == 204
    assert idp_admin.ended == ["phone"]
    assert next_call.status_code == 401
    assert next_call.json()["detail"] == "session revoked"
    assert (await client.get("/v1/me", headers=auth(**ALICE, sid="laptop"))).status_code == 200


async def test_users_cannot_revoke_someone_elses_session(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    idp_admin.live[CAROL["sub"]] = ["carols-laptop"]

    response = await client.delete("/v1/me/sessions/carols-laptop", headers=auth(**ALICE))

    assert response.status_code == 404
    assert idp_admin.ended == []


async def test_sign_out_everywhere_else_keeps_the_current_session(
    client: AsyncClient, auth: Auth, idp_admin: FakeIdpAdmin
) -> None:
    idp_admin.live[ALICE["sub"]] = ["laptop", "phone", "tablet"]

    result = await client.post("/v1/me/sessions/revoke-others", headers=auth(**ALICE, sid="laptop"))

    assert result.json() == {"revoked": 2}
    assert (await client.get("/v1/me", headers=auth(**ALICE, sid="tablet"))).status_code == 401
    assert (await client.get("/v1/me", headers=auth(**ALICE, sid="laptop"))).status_code == 200
