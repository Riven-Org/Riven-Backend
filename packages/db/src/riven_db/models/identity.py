"""Identity tables owned by the api-gateway (ADR 0003, ADR 0013).

These are global (not row-level-secured): authentication has to find the user, their
memberships and API keys before any org context exists. The identity service always filters
them explicitly by user or org.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from riven_db.base import Base, uuid_pk

GLOBAL = {"tenant_scoped": False}


class User(Base):
    """A person, provisioned on first sign-in from the identity provider's token."""

    __tablename__ = "users"
    __table_args__ = {"info": GLOBAL}

    id: Mapped[UUID] = uuid_pk()
    idp_subject: Mapped[str] = mapped_column(String(255), unique=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
