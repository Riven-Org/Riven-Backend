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
    # Development-only account, created on startup so the app can be tried without signing up.
    # Sign in with the username or the email. Refused outside dev/test.
    demo_user_enabled: bool = True
    demo_username: str = "Abubakar"
    demo_email: str = "abubakar@riven.local"
    demo_password: SecretStr = SecretStr("12345")

    @property
    def is_deployed(self) -> bool:
        return self.env in {"staging", "prod"}

    @property
    def demo_user_active(self) -> bool:
        return self.demo_user_enabled and not self.is_deployed

    @model_validator(mode="after")
    def _no_dev_credentials_when_deployed(self) -> Self:
        if self.is_deployed and self.jwt_secret.get_secret_value() == DEV_JWT_SECRET:
            raise ValueError(f"RIVEN_JWT_SECRET must be set for env={self.env}")
        if self.is_deployed and self.demo_user_enabled:
            raise ValueError(f"RIVEN_DEMO_USER_ENABLED must be false for env={self.env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
