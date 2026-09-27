"""The only module allowed to touch the causal graph tables (S03.2.3).

Every method is scoped to one org, on top of row-level security, so a graph query can never
cross tenants even from a connection that bypasses RLS. `test_graph_access.py` fails if any
other source file mentions the graph tables or models.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from riven_db.models.graph import GraphEdge, GraphNode
from riven_schemas import GraphConsistencyReport, NodeKind


@dataclass(frozen=True)
class Reached:
    node_id: UUID
    depth: int


class GraphRepository:
    def __init__(self, session: AsyncSession, org_id: str) -> None:
        if not org_id:
            raise ValueError("graph access requires an org_id")
        self._session = session
        self.org_id = org_id

    async def upsert_node(
        self,
        kind: NodeKind,
        key: str,
        label: str = "",
        properties: dict[str, Any] | None = None,
    ) -> UUID:
        """Create the node for (kind, key) or update its label; return its id."""
        statement = (
            insert(GraphNode)
            .values(
                org_id=self.org_id,
                kind=kind.value,
                key=key,
                label=label,
                properties=properties or {},
            )
            .on_conflict_do_update(index_elements=["org_id", "kind", "key"], set_={"label": label})
            .returning(GraphNode.id)
        )
        node_id: UUID = (await self._session.execute(statement)).scalar_one()
        return node_id

    async def add_edge(
        self,
        source_id: UUID,
        kind: str,
        target_id: UUID,
        *,
        provenance: str,
        created_by: str,
        confidence: float = 1.0,
    ) -> UUID:
        await self._require_nodes(source_id, target_id)
        edge = GraphEdge(
            org_id=self.org_id,
            kind=kind,
            source_id=source_id,
            target_id=target_id,
            provenance=provenance,
            confidence=confidence,
            created_by=created_by,
        )
        self._session.add(edge)
        await self._session.flush()
        return edge.id

    async def close_edge(self, edge_id: UUID) -> None:
        """Edges are closed, never deleted, so history stays explainable."""
        edge = await self._session.scalar(
            select(GraphEdge).where(GraphEdge.org_id == self.org_id, GraphEdge.id == edge_id)
        )
        if edge is None:
            raise LookupError(f"edge {edge_id} not found")
        edge.valid_to = datetime.now(UTC)
        await self._session.flush()

    async def neighbors(self, node_id: UUID) -> list[UUID]:
        """Nodes linked to `node_id` by a currently valid edge, in either direction."""
        rows = await self._session.execute(
            select(GraphEdge.source_id, GraphEdge.target_id).where(
                GraphEdge.org_id == self.org_id,
                GraphEdge.valid_to.is_(None),
                (GraphEdge.source_id == node_id) | (GraphEdge.target_id == node_id),
            )
        )
        return [t if s == node_id else s for s, t in rows.all()]

    async def reachable(self, node_id: UUID, max_depth: int = 5) -> list[Reached]:
        """Everything reachable from `node_id` over valid edges (either direction)."""
        rows = await self._session.execute(
            text(
                """
                WITH RECURSIVE walk(node_id, depth) AS (
                    SELECT CAST(:start AS uuid), 0
                    UNION
                    SELECT CASE WHEN e.source_id = w.node_id THEN e.target_id
                                ELSE e.source_id END,
                           w.depth + 1
                    FROM walk w
                    JOIN graph_edges e
                      ON (e.source_id = w.node_id OR e.target_id = w.node_id)
                     AND e.org_id = :org AND e.valid_to IS NULL
                    WHERE w.depth < :max_depth
                )
                SELECT node_id, min(depth) AS depth FROM walk
                WHERE node_id <> CAST(:start AS uuid)
                GROUP BY node_id ORDER BY depth, node_id
                """
            ),
            {"start": node_id, "org": self.org_id, "max_depth": max_depth},
        )
        return [Reached(node_id=r.node_id, depth=r.depth) for r in rows]

    async def _require_nodes(self, *node_ids: UUID) -> None:
        found = set(
            await self._session.scalars(
                select(GraphNode.id).where(
                    GraphNode.org_id == self.org_id, GraphNode.id.in_(node_ids)
                )
            )
        )
        missing = set(node_ids) - found
        if missing:
            raise LookupError(f"nodes not in org {self.org_id}: {sorted(map(str, missing))}")


async def count_orphaned_edges_all_orgs(session: AsyncSession) -> GraphConsistencyReport:
    """System-wide consistency check (S01.4.4): edges whose endpoint is missing or belongs to
    another org. Deliberately cross-org; only the nightly job calls it."""
    row = (
        await session.execute(
            text(
                """
                SELECT count(*) AS checked,
                       count(*) FILTER (
                           WHERE s.id IS NULL OR t.id IS NULL
                              OR s.org_id <> e.org_id OR t.org_id <> e.org_id
                       ) AS orphaned
                FROM graph_edges e
                LEFT JOIN graph_nodes s ON s.id = e.source_id
                LEFT JOIN graph_nodes t ON t.id = e.target_id
                """
            )
        )
    ).one()
    return GraphConsistencyReport(
        checked_edges=row.checked, orphaned_edges=row.orphaned, checked_at=datetime.now(UTC)
    )
