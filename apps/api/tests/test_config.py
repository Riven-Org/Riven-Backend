"""S02.2: API settings validation, staging/prod constraints, and CORS origin checks."""

import os
from pathlib import Path

import pytest

from riven_api.config import Settings
from riven_config import ConfigError, Environment

REAL_DB = "postgresql+asyncpg://app:s3cr3t-from-vault@db.internal:5432/riven"
REAL_REDIS = "redis://redis.internal:6379/0"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate from the developer's environment and .env file."""
    for key in list(os.environ):
        if key.startswith("RIVEN_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)


def test_api_defaults_work_for_local_development() -> None:
    settings = Settings.load()
    assert settings.env is Environment.DEV
    assert settings.cors_origins == ["http://localhost:5173"]
    assert settings.keycloak_admin_client_secret.get_secret_value() == "riven-dev-secret"


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_api_refuses_dev_credentials_in_deployed_environments(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("RIVEN_ENV", env)
    with pytest.raises(ConfigError, match="uses a development credential"):
        Settings.load()


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_api_refuses_http_cors_origins_in_deployed_environments(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("RIVEN_ENV", env)
    monkeypatch.setenv("RIVEN_DATABASE_URL", REAL_DB)
    monkeypatch.setenv("RIVEN_REDIS_URL", REAL_REDIS)
    monkeypatch.setenv("RIVEN_KEYCLOAK_ADMIN_CLIENT_SECRET", "prod-secret-from-vault")
    monkeypatch.setenv("RIVEN_CORS_ORIGINS", '["http://insecure-origin.com"]')

    with pytest.raises(ConfigError, match="RIVEN_CORS_ORIGINS must all be https://"):
        Settings.load()


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_api_accepts_valid_deployed_configuration(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("RIVEN_ENV", env)
    monkeypatch.setenv("RIVEN_DATABASE_URL", REAL_DB)
    monkeypatch.setenv("RIVEN_REDIS_URL", REAL_REDIS)
    monkeypatch.setenv("RIVEN_KEYCLOAK_ADMIN_CLIENT_SECRET", "prod-secret-from-vault")
    monkeypatch.setenv("RIVEN_CORS_ORIGINS", '["https://app.riven.dev"]')

    settings = Settings.load()
    assert settings.env.value == env
    assert settings.is_deployed is True
    assert settings.cors_origins == ["https://app.riven.dev"]


def test_oidc_jwks_url_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings.load()
    assert (
        settings.oidc_jwks_url == "http://localhost:8081/realms/riven/protocol/openid-connect/certs"
    )

    monkeypatch.setenv(
        "RIVEN_OIDC_JWKS_URL_OVERRIDE",
        "http://keycloak:8080/realms/riven/protocol/openid-connect/certs",
    )
    overridden = Settings.load()
    assert (
        overridden.oidc_jwks_url
        == "http://keycloak:8080/realms/riven/protocol/openid-connect/certs"
    )
