"""S03.2.3: all graph access goes through one org-scoped repository.
Needs Postgres (RIVEN_TEST_DATABASE_URL)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from riven_db.graph_repository import GraphRepository
from riven_schemas import NodeKind


async def test_traversal_follows_valid_edges_within_the_org(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        graph = GraphRepository(session, "org_a")
        change = await graph.upsert_node(NodeKind.CHANGE, "c1")
        bug = await graph.upsert_node(NodeKind.BUG, "b1")
        fix = await graph.upsert_node(NodeKind.FIX, "f1")
        await graph.add_edge(change, "introduced", bug, provenance="t", created_by="t")
        await graph.add_edge(fix, "fixes", bug, provenance="t", created_by="t")

        reached = await graph.reachable(change)

    assert [(r.node_id, r.depth) for r in reached] == sorted(
        [(bug, 1), (fix, 2)], key=lambda x: (x[1], x[0])
    )


async def test_closed_edges_are_kept_but_not_traversed(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        graph = GraphRepository(session, "org_a")
        a = await graph.upsert_node(NodeKind.MODULE, "a.py")
        b = await graph.upsert_node(NodeKind.TEST, "test_a")
        edge = await graph.add_edge(a, "tested_by", b, provenance="t", created_by="t")

        await graph.close_edge(edge)

        assert await graph.neighbors(a) == []


async def test_other_orgs_nodes_are_invisible_and_cannot_be_linked(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session, session.begin():
        ours = GraphRepository(session, "org_a")
        theirs = GraphRepository(session, "org_b")
        mine = await ours.upsert_node(NodeKind.BUG, "b1")
        foreign = await theirs.upsert_node(NodeKind.BUG, "b1")

        with pytest.raises(LookupError, match="not in org org_a"):
            await ours.add_edge(mine, "same_as", foreign, provenance="t", created_by="t")
        assert await ours.reachable(foreign) == []
        assert mine != foreign


async def test_upsert_is_idempotent(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session, session.begin():
        graph = GraphRepository(session, "org_a")
        first = await graph.upsert_node(NodeKind.REQUIREMENT, "REQ-1", "old")
        second = await graph.upsert_node(NodeKind.REQUIREMENT, "REQ-1", "new")

    assert first == second


def test_graph_repository_requires_an_org() -> None:
    with pytest.raises(ValueError):
        GraphRepository(None, "")  # type: ignore[arg-type]
