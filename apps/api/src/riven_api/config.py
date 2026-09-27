from functools import lru_cache
from typing import Self

from pydantic import model_validator

from riven_config import DatabaseSettings, RedisSettings, TemporalSettings


class Settings(DatabaseSettings, RedisSettings, TemporalSettings):
    """API settings, validated at startup (ticket S02.2)."""

    cors_origins: list[str] = ["http://localhost:5173"]
    # OIDC (Keycloak, S03.1). The issuer must match the `iss` claim exactly; the JWKS URL may
    # differ when the API reaches the IdP on an internal hostname (docker-compose).
    oidc_issuer: str = "http://localhost:8081/realms/riven"
    oidc_audience: str = "riven-api"
    oidc_jwks_url_override: str | None = None

    @property
    def oidc_jwks_url(self) -> str:
        return self.oidc_jwks_url_override or f"{self.oidc_issuer}/protocol/openid-connect/certs"

    @model_validator(mode="after")
    def _https_origins_when_deployed(self) -> Self:
        if self.is_deployed and any(not o.startswith("https://") for o in self.cors_origins):
            raise ValueError(f"RIVEN_CORS_ORIGINS must all be https:// for env={self.env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings.load()
