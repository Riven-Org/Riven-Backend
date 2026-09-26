"""Tables owned by the memory service (ADR 0008)."""

from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from riven_db.base import Base, TenantMixin, uuid_pk


class Bug(TenantMixin, Base):
    __tablename__ = "bugs"
    __table_args__ = (UniqueConstraint("org_id", "repository_id", "fingerprint"),)

    id: Mapped[UUID] = uuid_pk()
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"))
    fingerprint: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(16))
    severity: Mapped[str] = mapped_column(String(16))
    module: Mapped[str | None] = mapped_column(String(500))
    first_seen_change_id: Mapped[UUID] = mapped_column(ForeignKey("changes.id"))
    occurrences: Mapped[int] = mapped_column(default=1)


class RegressionLock(TenantMixin, Base):
    __tablename__ = "regression_locks"

    id: Mapped[UUID] = uuid_pk()
    bug_id: Mapped[UUID] = mapped_column(ForeignKey("bugs.id"), index=True)
    test_ref: Mapped[str] = mapped_column(String(1000))
    fixed_by_change_id: Mapped[UUID] = mapped_column(ForeignKey("changes.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")
