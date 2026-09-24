from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings loaded from the environment / .env (ticket S02.2)."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIVEN_", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://riven:riven@localhost:5432/riven"
    redis_url: str = "redis://localhost:6379/0"
    temporal_address: str = "localhost:7233"
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
