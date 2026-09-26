from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TenantMixin:
    """Every domain table is scoped to an org (tickets S01.4, S03.2)."""

    org_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def uuid_pk() -> Mapped[UUID]:
    return mapped_column(primary_key=True, server_default=text("gen_random_uuid()"))
