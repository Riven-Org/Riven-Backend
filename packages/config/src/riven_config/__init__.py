"""Typed, fail-fast settings for every Riven service (ticket S02.2, ADR 0012).

Values come from, in order of precedence: environment variables (`RIVEN_*`), secret files in
`RIVEN_SECRETS_DIR` (one file per setting, e.g. `riven_database_url`, as mounted by Docker
secrets or the Kubernetes Secrets Store CSI driver), then `.env`. Secrets are `SecretStr`, so
they never appear in logs or reprs. Outside dev/test, development credentials are rejected.

Each service composes the blocks it needs and calls `.load()` at startup; an invalid
configuration stops the process with a readable message instead of failing later.
"""

import os
from enum import StrEnum
from typing import Any, Self

from pydantic import SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that only ever belong in local development (docker-compose.yml, .env.example).
DEV_CREDENTIALS = ("riven-dev-secret", "riven:riven@", "change-me")


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class ConfigError(SystemExit):
    """Raised by `load()`; exits the process with the message and status 1."""


class RivenSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIVEN_", extra="ignore")

    env: Environment = Environment.DEV

    @property
    def is_deployed(self) -> bool:
        return self.env in (Environment.STAGING, Environment.PROD)

    @model_validator(mode="after")
    def _no_dev_credentials_when_deployed(self) -> Self:
        if self.is_deployed:
            for name, value in self:
                raw = value.get_secret_value() if isinstance(value, SecretStr) else value
                if isinstance(raw, str) and any(marker in raw for marker in DEV_CREDENTIALS):
                    raise ValueError(
                        f"RIVEN_{name.upper()} uses a development credential; "
                        f"set a real value for env={self.env}"
                    )
        return self

    @classmethod
    def load(cls, **overrides: Any) -> Self:
        """Build the settings or exit with a readable error (fail fast at startup)."""
        secrets_dir = os.environ.get("RIVEN_SECRETS_DIR")
        if secrets_dir and not os.path.isdir(secrets_dir):
            raise ConfigError(f"Invalid configuration: RIVEN_SECRETS_DIR={secrets_dir} not found")
        try:
            if secrets_dir:
                return cls(_secrets_dir=secrets_dir, **overrides)
            return cls(**overrides)
        except ValidationError as exc:
            problems = "\n".join(
                f"  - {'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg']}"
                for e in exc.errors()
            )
            raise ConfigError(f"Invalid configuration for {cls.__name__}:\n{problems}") from None


class DatabaseSettings(RivenSettings):
    database_url: SecretStr = SecretStr("postgresql+asyncpg://riven:riven@localhost:5432/riven")

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("must start with postgresql+asyncpg://")
        return value


class RedisSettings(RivenSettings):
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    @field_validator("redis_url")
    @classmethod
    def _redis_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("must start with redis:// or rediss://")
        return value


class TemporalSettings(RivenSettings):
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"


class StorageSettings(RivenSettings):
    """S3-compatible object storage; leave the endpoint empty for AWS S3."""

    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket: str = "riven-artifacts"
    s3_access_key: str = "riven"
    s3_secret_key: SecretStr = SecretStr("riven-dev-secret")


__all__ = [
    "DEV_CREDENTIALS",
    "ConfigError",
    "DatabaseSettings",
    "Environment",
    "RedisSettings",
    "RivenSettings",
    "StorageSettings",
    "TemporalSettings",
]
