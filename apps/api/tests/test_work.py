from typing import Any

from fastapi.testclient import TestClient


def _auth(client: TestClient, email: str = "ada@example.com") -> dict[str, str]:
    body = {"name": "Ada", "email": email, "password": "analytical-engine"}
    token = client.post("/v1/auth/signup", json=body).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _project(client: TestClient, auth: dict[str, str], name: str = "shop") -> dict[str, Any]:
    response = client.post("/v1/projects", json={"name": name}, headers=auth)
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _change(
    client: TestClient, auth: dict[str, str], project_id: str, producer: str = "ai_agent"
) -> dict[str, Any]:
    response = client.post(
        "/v1/changes",
        json={"project_id": project_id, "commit": "a3f9c12", "title": "feat", "producer": producer},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def test_everything_needs_a_signed_in_user(client: TestClient) -> None:
    for path in ("/v1/dashboard", "/v1/projects", "/v1/changes", "/v1/bugs"):
        assert client.get(path).status_code == 401


def test_project_names_are_unique_per_user(client: TestClient) -> None:
    auth = _auth(client)
    _project(client, auth, "Shop")

    again = client.post("/v1/projects", json={"name": "shop"}, headers=auth)

    assert again.status_code == 409
    assert [p["name"] for p in client.get("/v1/projects", headers=auth).json()] == ["Shop"]


def test_you_cannot_judge_a_human_change_you_logged(client: TestClient) -> None:
    auth = _auth(client)
    change = _change(client, auth, _project(client, auth)["id"], producer="human")

    response = client.post(
        f"/v1/changes/{change['id']}/verdict", json={"verdict": "passed"}, headers=auth
    )

    assert change["self_produced"] is True
    assert response.status_code == 409
    assert "never approves its own work" in response.json()["detail"]


def test_a_failed_verdict_records_a_bug(client: TestClient) -> None:
    auth = _auth(client)
    project = _project(client, auth)
    change = _change(client, auth, project["id"])
    url = f"/v1/changes/{change['id']}/verdict"

    no_bug = client.post(url, json={"verdict": "failed"}, headers=auth)
    failed = client.post(
        url,
        json={"verdict": "failed", "bug_title": "Total off by 0.01", "bug_severity": "high"},
        headers=auth,
    )
    again = client.post(url, json={"verdict": "passed"}, headers=auth)

    assert no_bug.status_code == 422
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert again.status_code == 409
    bugs = client.get("/v1/bugs", headers=auth).json()
    assert [(b["title"], b["severity"], b["status"]) for b in bugs] == [
        ("Total off by 0.01", "high", "open")
    ]


def test_only_a_passing_change_in_the_same_project_fixes_a_bug(client: TestClient) -> None:
    auth = _auth(client)
    project = _project(client, auth)
    other = _project(client, auth, "other")
    broken = _change(client, auth, project["id"])
    client.post(
        f"/v1/changes/{broken['id']}/verdict",
        json={"verdict": "failed", "bug_title": "Crash"},
        headers=auth,
    )
    bug = client.get("/v1/bugs", headers=auth).json()[0]
    pending = _change(client, auth, project["id"])
    elsewhere = _change(client, auth, other["id"])
    client.post(f"/v1/changes/{elsewhere['id']}/verdict", json={"verdict": "passed"}, headers=auth)
    fix = _change(client, auth, project["id"])
    client.post(f"/v1/changes/{fix['id']}/verdict", json={"verdict": "passed"}, headers=auth)
    url = f"/v1/bugs/{bug['id']}/fix"

    assert client.post(url, json={"change_id": pending["id"]}, headers=auth).status_code == 422
    assert client.post(url, json={"change_id": elsewhere["id"]}, headers=auth).status_code == 422
    fixed = client.post(url, json={"change_id": fix["id"]}, headers=auth)
    assert fixed.status_code == 200
    assert (fixed.json()["status"], fixed.json()["fixed_by_commit"]) == ("fixed", "a3f9c12")
    assert client.post(url, json={}, headers=auth).status_code == 409


def test_users_never_see_each_others_work(client: TestClient) -> None:
    ada = _auth(client)
    bob = _auth(client, "bob@example.com")
    project = _project(client, ada)
    change = _change(client, ada, project["id"])

    assert client.get("/v1/projects", headers=bob).json() == []
    assert client.get("/v1/changes", headers=bob).json() == []
    assert client.delete(f"/v1/projects/{project['id']}", headers=bob).status_code == 404
    verdict = client.post(
        f"/v1/changes/{change['id']}/verdict", json={"verdict": "passed"}, headers=bob
    )
    assert verdict.status_code == 404
    log = client.post(
        "/v1/changes",
        json={"project_id": project["id"], "commit": "abcd", "title": "x", "producer": "bot"},
        headers=bob,
    )
    assert log.status_code == 404


def test_dashboard_summarises_real_activity(client: TestClient) -> None:
    auth = _auth(client)
    project = _project(client, auth)
    empty = client.get("/v1/dashboard", headers=auth).json()
    for verdict in ("passed", "passed", "passed", "failed"):
        change = _change(client, auth, project["id"])
        client.post(
            f"/v1/changes/{change['id']}/verdict",
            json={"verdict": verdict, "bug_title": "Bug"},
            headers=auth,
        )
    _change(client, auth, project["id"], producer="human")

    summary = client.get("/v1/dashboard", headers=auth).json()

    assert empty["pass_rate"] is None
    assert len(empty["trend"]) == 7
    assert summary["totals"] == {
        "projects": 1,
        "changes": 5,
        "pending": 1,
        "passed": 3,
        "failed": 1,
        "needs_review": 0,
        "open_bugs": 1,
        "fixed_bugs": 0,
    }
    assert summary["pass_rate"] == 0.75
    assert summary["by_producer"] == {"human": 1, "ai_agent": 4, "bot": 0}
    today = summary["trend"][-1]
    assert (today["logged"], today["passed"], today["failed"]) == (5, 3, 1)
    assert summary["kpis"]["changes"] == {"value": 5, "previous": 0, "series": [0] * 6 + [5]}
    assert summary["kpis"]["verified"]["value"] == 4
    assert summary["kpis"]["bugs"]["value"] == 1
    assert summary["kpis"]["memories"]["series"][-1] == 1
    assert len(summary["recent"]) == 5
    assert [c["status"] for c in summary["active"]] == ["pending"]
    assert len(summary["runs"]) == 4
    assert len(summary["open_bugs"]) == len(summary["chains"]) == 1
    assert len(client.get("/v1/dashboard?days=30", headers=auth).json()["trend"]) == 30
    assert client.get("/v1/dashboard?days=9", headers=auth).status_code == 422


def test_deleting_a_project_removes_its_changes_and_bugs(client: TestClient) -> None:
    auth = _auth(client)
    project = _project(client, auth)
    change = _change(client, auth, project["id"])
    client.post(
        f"/v1/changes/{change['id']}/verdict",
        json={"verdict": "failed", "bug_title": "Crash"},
        headers=auth,
    )

    assert client.delete(f"/v1/projects/{project['id']}", headers=auth).status_code == 204
    assert client.get("/v1/changes", headers=auth).json() == []
    assert client.get("/v1/bugs", headers=auth).json() == []


def test_timestamps_are_utc_with_an_offset(client: TestClient) -> None:
    auth = _auth(client)

    project = _project(client, auth)
    me = client.get("/v1/me", headers=auth).json()

    assert project["created_at"].endswith(("Z", "+00:00"))
    assert me["created_at"].endswith(("Z", "+00:00"))


def test_changes_and_bugs_are_numbered_per_user(client: TestClient) -> None:
    ada = _auth(client)
    bob = _auth(client, "bob@example.com")
    first = _change(client, ada, _project(client, ada)["id"])
    second = _change(client, ada, first["project_id"])
    bobs = _change(client, bob, _project(client, bob)["id"])

    assert (first["number"], second["number"], bobs["number"]) == (1, 2, 1)
    numbers = [c["number"] for c in client.get("/v1/changes", headers=ada).json()]
    assert numbers == [2, 1]


def test_dashboard_and_lists_filter_by_project(client: TestClient) -> None:
    auth = _auth(client)
    shop = _project(client, auth, "shop")
    blog = _project(client, auth, "blog")
    _change(client, auth, shop["id"])
    _change(client, auth, blog["id"])
    _change(client, auth, blog["id"])

    summary = client.get(f"/v1/dashboard?project_id={blog['id']}", headers=auth).json()
    stranger = _auth(client, "eve@example.com")

    assert summary["totals"]["changes"] == 2
    assert len(client.get(f"/v1/changes?project_id={shop['id']}", headers=auth).json()) == 1
    assert client.get(f"/v1/dashboard?project_id={blog['id']}", headers=stranger).status_code == 404


def test_activity_lists_what_happened_newest_first(client: TestClient) -> None:
    auth = _auth(client)
    change = _change(client, auth, _project(client, auth)["id"])
    client.post(
        f"/v1/changes/{change['id']}/verdict",
        json={"verdict": "failed", "bug_title": "Crash on checkout"},
        headers=auth,
    )

    kinds = [i["kind"] for i in client.get("/v1/activity", headers=auth).json()]

    assert sorted(kinds) == ["bug_found", "change_logged", "verdict"]
    assert kinds[-1] == "change_logged"
