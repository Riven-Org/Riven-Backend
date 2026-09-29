"""S02.2: typed settings validated at startup, secrets from files, no dev credentials when
deployed."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from riven_config import (
    ConfigError,
    DatabaseSettings,
    Environment,
    RedisSettings,
    StorageSettings,
)

REAL_DB = "postgresql+asyncpg://app:s3cr3t-from-vault@db.internal:5432/riven"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate from the developer's environment and .env file."""
    for key in list(os.environ):
        if key.startswith("RIVEN_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)


def test_defaults_work_for_local_development() -> None:
    settings = DatabaseSettings.load()

    assert settings.env is Environment.DEV
    assert settings.database_url.get_secret_value().startswith("postgresql+asyncpg://")


def test_unknown_environment_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIVEN_ENV", "production")

    with pytest.raises(ConfigError, match="env"):
        DatabaseSettings.load()


def test_wrong_database_driver_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIVEN_DATABASE_URL", "postgresql://riven@localhost/riven")

    with pytest.raises(ConfigError, match="postgresql\\+asyncpg"):
        DatabaseSettings.load()


def test_wrong_redis_scheme_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIVEN_REDIS_URL", "http://localhost:6379")

    with pytest.raises(ConfigError, match="redis_url"):
        RedisSettings.load()


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_deployed_environments_refuse_development_credentials(
    monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("RIVEN_ENV", env)

    with pytest.raises(ConfigError, match="RIVEN_DATABASE_URL uses a development credential"):
        DatabaseSettings.load()


def test_deployed_environment_accepts_real_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIVEN_ENV", "prod")
    monkeypatch.setenv("RIVEN_DATABASE_URL", REAL_DB)

    assert DatabaseSettings.load().env is Environment.PROD


def test_secrets_are_read_from_mounted_files_and_never_printed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "riven_database_url").write_text(REAL_DB)
    monkeypatch.setenv("RIVEN_SECRETS_DIR", str(secrets))

    settings = DatabaseSettings.load()

    assert settings.database_url.get_secret_value() == REAL_DB
    assert "s3cr3t" not in repr(settings)
    assert "s3cr3t" not in str(settings.model_dump())


def test_rotating_a_secret_file_needs_no_code_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    secret_file = secrets / "riven_s3_secret_key"
    secret_file.write_text("old-key")
    monkeypatch.setenv("RIVEN_SECRETS_DIR", str(secrets))
    assert StorageSettings.load().s3_secret_key.get_secret_value() == "old-key"

    secret_file.write_text("rotated-key")  # what the secrets manager / CSI driver does

    assert StorageSettings.load().s3_secret_key.get_secret_value() == "rotated-key"


def test_environment_variable_overrides_secret_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "riven_s3_bucket").write_text("from-file")
    monkeypatch.setenv("RIVEN_SECRETS_DIR", str(secrets))
    monkeypatch.setenv("RIVEN_S3_BUCKET", "from-env")

    assert StorageSettings.load().s3_bucket == "from-env"


def test_missing_secrets_dir_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RIVEN_SECRETS_DIR", "/nonexistent/riven")

    with pytest.raises(ConfigError, match="RIVEN_SECRETS_DIR"):
        DatabaseSettings.load()


# --- every service refuses to start with invalid config --------------------------------

SERVICES = {
    "api": [sys.executable, "-c", "import riven_api.main"],
    "worker": [sys.executable, "-m", "riven_worker.main"],
    "relay": [sys.executable, "-m", "riven_events.relay"],
    "storage": [sys.executable, "-m", "riven_storage"],
}


@pytest.mark.parametrize("service", sorted(SERVICES))
def test_service_refuses_to_start_with_invalid_config(service: str, tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("RIVEN_")}
    env["RIVEN_ENV"] = "prod"  # with the dev defaults still in place

    result = subprocess.run(
        SERVICES[service], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60
    )

    assert result.returncode == 1
    assert "Invalid configuration" in result.stderr
    assert "development credential" in result.stderr
    assert "Traceback" not in result.stderr
