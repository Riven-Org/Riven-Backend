"""S01.4.4: the consistency checker reports zero orphaned edges on a consistent demo graph and
counts edges that cross tenants. Needs Postgres (RIVEN_TEST_DATABASE_URL)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from riven_db.models import GraphEdge, GraphNode
from riven_worker.graph_consistency import (
    GraphConsistencyActivities,
    GraphConsistencyWorkflow,
    count_orphaned_edges,
)

CHAIN = ["requirement", "change", "module", "bug", "fix", "test"]


async def _demo_graph(sessions: async_sessionmaker[AsyncSession], org_id: str) -> list[GraphNode]:
    """requirement → change → module → bug → fix → test, as the MVP scenario links them."""
    async with sessions() as session, session.begin():
        nodes = [GraphNode(org_id=org_id, kind=k, key=f"{k}-1", label=k) for k in CHAIN]
        session.add_all(nodes)
        await session.flush()
        for source, target in zip(nodes, nodes[1:], strict=False):
            session.add(
                GraphEdge(
                    org_id=org_id,
                    kind=f"{source.kind}_to_{target.kind}",
                    source_id=source.id,
                    target_id=target.id,
                    provenance="test",
                    confidence=1.0,
                    created_by="riven-graph",
                )
            )
    return nodes


async def test_demo_graph_has_zero_orphaned_edges(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _demo_graph(sessions, "org_a")

    async with sessions() as session:
        report = await count_orphaned_edges(session)

    assert report.checked_edges == len(CHAIN) - 1
    assert report.orphaned_edges == 0


async def test_edge_linking_another_orgs_node_is_reported_as_orphaned(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    ours = await _demo_graph(sessions, "org_a")
    theirs = await _demo_graph(sessions, "org_b")
    async with sessions() as session, session.begin():
        session.add(
            GraphEdge(
                org_id="org_a",
                kind="bad_link",
                source_id=ours[0].id,
                target_id=theirs[0].id,
                provenance="test",
                confidence=0.5,
                created_by="bulk-import",
            )
        )

    async with sessions() as session:
        report = await count_orphaned_edges(session)

    assert report.orphaned_edges == 1


async def test_consistency_workflow_returns_the_report(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    await _demo_graph(sessions, "org_a")
    activities = GraphConsistencyActivities(sessions)
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[GraphConsistencyWorkflow],
            activities=[activities.check_graph_consistency],
        ):
            report = await env.client.execute_workflow(
                GraphConsistencyWorkflow.run, id=str(uuid.uuid4()), task_queue=task_queue
            )

    assert report.orphaned_edges == 0
    assert report.checked_edges == len(CHAIN) - 1
