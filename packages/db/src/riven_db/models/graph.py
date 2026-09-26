"""Causal graph tables owned by the graph service (ADR 0009, ADR 0001: Postgres, no Neo4j).

Edges carry provenance and are closed by setting `valid_to`, never deleted.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from riven_db.base import Base, TenantMixin, uuid_pk


class GraphNode(TenantMixin, Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (UniqueConstraint("org_id", "kind", "key"),)

    id: Mapped[UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(32))
    key: Mapped[str] = mapped_column(String(1000))
    label: Mapped[str] = mapped_column(String(500), default="")
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class GraphEdge(TenantMixin, Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        Index("ix_graph_edges_org_source", "org_id", "source_id"),
        Index("ix_graph_edges_org_target", "org_id", "target_id"),
    )

    id: Mapped[UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(64))
    source_id: Mapped[UUID] = mapped_column(ForeignKey("graph_nodes.id"))
    target_id: Mapped[UUID] = mapped_column(ForeignKey("graph_nodes.id"))
    provenance: Mapped[str] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Float)
    created_by: Mapped[str] = mapped_column(String(255))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
