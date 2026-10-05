from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from riven_api.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


def _now() -> datetime:
    return datetime.now(UTC)


def _id() -> str:
    return str(uuid4())


class Project(Base):
    """A codebase whose changes are verified. Owned by one user; every query filters by owner."""

    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    repo_url: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Change(Base):
    """A commit or PR logged for verification, and the verdict it received."""

    __tablename__ = "changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    commit: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    producer: Mapped[str] = mapped_column(String(16))  # ProducerKind
    author: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # Verdict
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), default=None)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class Bug(Base):
    """A problem found when a change failed verification; open until a passing change fixes it."""

    __tablename__ = "bugs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    change_id: Mapped[str] = mapped_column(ForeignKey("changes.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(String(16))  # Severity
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    fixed_by_change_id: Mapped[str | None] = mapped_column(
        ForeignKey("changes.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
