"""Identity tables owned by the api-gateway (ADR 0003, ADR 0013).

These are global (not row-level-secured): authentication has to find the user, their
memberships and API keys before any org context exists. The identity service always filters
them explicitly by user or org.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
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


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = {"info": GLOBAL}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    require_mfa: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = {"info": GLOBAL}

    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = {"info": GLOBAL}

    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    invited_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceAccount(Base):
    """A non-human identity (AI agent, CI system, bot) that acts in one org (S03.4)."""

    __tablename__ = "service_accounts"
    __table_args__ = {"info": GLOBAL}

    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(16))
    agent_model: Mapped[str | None] = mapped_column(String(128))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(Base):
    """A scoped, expiring secret for a service account. Only an Argon2 hash is stored."""

    __tablename__ = "api_keys"
    __table_args__ = {"info": GLOBAL}

    id: Mapped[UUID] = uuid_pk()
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    service_account_id: Mapped[UUID] = mapped_column(ForeignKey("service_accounts.id"), index=True)
    prefix: Mapped[str] = mapped_column(String(16), unique=True)
    secret_hash: Mapped[str] = mapped_column(String(255))
    scopes: Mapped[list[str]] = mapped_column(JSONB)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
