"""Shared persistence for Riven services (ticket S01.4, ADR 0011)."""

from riven_db import models
from riven_db.base import Base, TenantMixin, tenant_tables

__all__ = ["Base", "TenantMixin", "models", "tenant_tables"]
