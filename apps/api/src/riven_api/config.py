from functools import lru_cache
from typing import Self

from pydantic import model_validator

from riven_config import DatabaseSettings, RedisSettings, TemporalSettings


class Settings(DatabaseSettings, RedisSettings, TemporalSettings):
    """API settings, validated at startup (ticket S02.2)."""

    cors_origins: list[str] = ["http://localhost:5173"]

    @model_validator(mode="after")
    def _https_origins_when_deployed(self) -> Self:
        if self.is_deployed and any(not o.startswith("https://") for o in self.cors_origins):
            raise ValueError(f"RIVEN_CORS_ORIGINS must all be https:// for env={self.env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings.load()
