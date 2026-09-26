from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class EventsBase(DeclarativeBase):
    """Metadata for the event backbone's own tables (migrated by apps/api/alembic)."""


class OutboxEvent(EventsBase):
    """An event waiting to be (or already) published. Written in the state change's transaction.

    Infrastructure table: the relay reads across orgs, so it is not row-level-secured.
    """

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_unpublished",
            "id",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    org_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessedEvent(EventsBase):
    """Which consumer has already handled which event (idempotency record)."""

    __tablename__ = "processed_events"

    consumer: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
