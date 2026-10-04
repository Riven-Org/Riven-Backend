from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from riven_api.config import Settings
from riven_api.db import get_session
from riven_api.main import create_app


class _BrokenSession:
    async def execute(self, *_: object) -> None:
        raise ConnectionError("database unreachable")


async def _broken_session() -> AsyncIterator[_BrokenSession]:
    yield _BrokenSession()


def test_health_returns_ok() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_503_when_database_is_down() -> None:
    app = create_app()
    app.dependency_overrides[get_session] = _broken_session

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json()["database"] == "down"


def test_deployed_envs_refuse_the_demo_user() -> None:
    with pytest.raises(ValidationError, match="RIVEN_DEMO_USER_ENABLED"):
        Settings(env="prod", jwt_secret=SecretStr("a-real-secret"), demo_user_enabled=True)
    Settings(env="prod", jwt_secret=SecretStr("a-real-secret"), demo_user_enabled=False)
