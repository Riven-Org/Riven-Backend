from pydantic_settings import BaseSettings, SettingsConfigDict


class EventSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="RIVEN_", extra="ignore")

    database_url: str = "postgresql+asyncpg://riven:riven@localhost:5432/riven"
    redis_url: str = "redis://localhost:6379/0"
    outbox_poll_seconds: float = 0.5
