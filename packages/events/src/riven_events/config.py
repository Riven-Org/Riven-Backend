from riven_config import DatabaseSettings, RedisSettings


class EventSettings(DatabaseSettings, RedisSettings):
    """Outbox relay settings, validated at startup (ticket S02.2)."""

    outbox_poll_seconds: float = 0.5
