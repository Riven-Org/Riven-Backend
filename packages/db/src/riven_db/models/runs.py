"""Tables owned by the orchestrator (ADR 0005) and sandbox-runner (ADR 0006)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from riven_db.base import Base, TenantMixin, uuid_pk


class VerificationRun(TenantMixin, Base):
    __tablename__ = "verification_runs"

    id: Mapped[UUID] = uuid_pk()
    change_id: Mapped[UUID] = mapped_column(ForeignKey("changes.id"), index=True)
    workflow_id: Mapped[str] = mapped_column(String(255), unique=True)
    state: Mapped[str] = mapped_column(String(16))
    verdict: Mapped[str | None] = mapped_column(String(16))
    verifier_identity: Mapped[str] = mapped_column(String(255))
    stages: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Artifact(TenantMixin, Base):
    """Metadata of a log or artifact; the bytes live in object storage, never on local disk."""

    __tablename__ = "artifacts"

    id: Mapped[UUID] = uuid_pk()
    run_id: Mapped[UUID] = mapped_column(ForeignKey("verification_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
