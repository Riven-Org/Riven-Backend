from functools import lru_cache
from typing import Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "riven-dev-secret-change-me-in-production"


class Settings(BaseSettings):
    """API settings from `RIVEN_*` environment variables or `.env`."""

    model_config = SettingsConfigDict(env_prefix="RIVEN_", env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "sqlite+aiosqlite:///./riven.db"
    cors_origins: list[str] = ["http://localhost:5173"]
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_ttl_minutes: int = 60 * 24

    @model_validator(mode="after")
    def _no_dev_secret_when_deployed(self) -> Self:
        if self.env in {"staging", "prod"} and self.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
            raise ValueError(f"RIVEN_JWT_SECRET must be set for env={self.env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
