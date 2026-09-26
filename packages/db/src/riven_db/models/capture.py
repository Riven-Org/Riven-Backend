"""Tables owned by the capture service (ADR 0004)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from riven_db.base import Base, TenantMixin, uuid_pk


class Repository(TenantMixin, Base):
    __tablename__ = "repositories"
    __table_args__ = (UniqueConstraint("org_id", "full_name"),)

    id: Mapped[UUID] = uuid_pk()
    full_name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(32), default="github")
    default_branch: Mapped[str] = mapped_column(String(255), default="main")


class Change(TenantMixin, Base):
    __tablename__ = "changes"
    __table_args__ = (UniqueConstraint("org_id", "repository_id", "commit_sha"),)

    id: Mapped[UUID] = uuid_pk()
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"))
    commit_sha: Mapped[str] = mapped_column(String(64))
    pr_number: Mapped[int | None]
    title: Mapped[str] = mapped_column(String(500), default="")
    branch: Mapped[str | None] = mapped_column(String(255))
    producer_kind: Mapped[str] = mapped_column(String(16))
    producer_identity: Mapped[str] = mapped_column(String(255))
    agent_model: Mapped[str | None] = mapped_column(String(128))
    files_changed: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
