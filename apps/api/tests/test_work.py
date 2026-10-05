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
    assert len(empty["daily"]) == 14
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
    assert (summary["daily"][-1]["logged"], summary["daily"][-1]["verified"]) == (5, 4)
    assert len(summary["recent"]) == 5
    assert len(summary["open_bugs"]) == 1


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
