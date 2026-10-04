from fastapi.testclient import TestClient

ADA = {"name": "Ada Lovelace", "email": "Ada@Example.com", "password": "analytical-engine"}


def _signup(client: TestClient, **overrides: str) -> dict[str, object]:
    response = client.post("/v1/auth/signup", json={**ADA, **overrides})
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


def test_signup_returns_a_token_and_the_user(client: TestClient) -> None:
    body = _signup(client)

    assert body["token_type"] == "bearer"
    user = body["user"]
    assert isinstance(user, dict)
    assert (user["name"], user["email"]) == ("Ada Lovelace", "ada@example.com")
    assert "password_hash" not in user


def test_signup_rejects_a_duplicate_email_in_any_case(client: TestClient) -> None:
    _signup(client)

    response = client.post("/v1/auth/signup", json={**ADA, "email": "ADA@example.com"})

    assert response.status_code == 409


def test_signup_rejects_a_short_password(client: TestClient) -> None:
    response = client.post("/v1/auth/signup", json={**ADA, "password": "short"})

    assert response.status_code == 422


def test_login_with_the_right_password(client: TestClient) -> None:
    _signup(client)

    response = client.post(
        "/v1/auth/login", json={"email": "ada@example.com", "password": ADA["password"]}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_with_a_wrong_password_or_unknown_email(client: TestClient) -> None:
    _signup(client)

    wrong = client.post("/v1/auth/login", json={"email": ADA["email"], "password": "nope-nope"})
    unknown = client.post("/v1/auth/login", json={"email": "x@example.com", "password": "whatever"})

    assert wrong.status_code == unknown.status_code == 401


def test_me_needs_a_valid_token(client: TestClient) -> None:
    token = _signup(client)["access_token"]

    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "ada@example.com"


def test_demo_user_signs_in_with_username_or_email(client: TestClient) -> None:
    by_name = client.post("/v1/auth/login", json={"identifier": "abubakar", "password": "12345"})
    by_email = client.post(
        "/v1/auth/login", json={"email": "abubakar@riven.local", "password": "12345"}
    )

    assert by_name.status_code == by_email.status_code == 200
    assert by_name.json()["user"]["name"] == "Abubakar"


def test_demo_user_wrong_password(client: TestClient) -> None:
    response = client.post("/v1/auth/login", json={"identifier": "Abubakar", "password": "nope"})

    assert response.status_code == 401
