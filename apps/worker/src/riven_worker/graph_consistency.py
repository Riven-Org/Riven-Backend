"""Nightly causal-graph consistency check (ticket S01.4.4).

An edge is orphaned when an endpoint node is missing or belongs to another org (a
cross-tenant link). Foreign keys prevent the first case today; the check still counts it so
the job stays valid if edges are ever bulk-loaded. The count is logged as
`graph_consistency orphaned_edges=N` and returned as the workflow result (visible in the
Temporal UI); exporting it as a metric is S23.1.
"""

import contextlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity, workflow
from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleSpec,
)

with workflow.unsafe.imports_passed_through():
    from riven_schemas import GraphConsistencyReport

SCHEDULE_ID = "graph-consistency-nightly"
NIGHTLY_CRON = "0 3 * * *"
log = logging.getLogger(__name__)

_ORPHANS_SQL = text(
    """
    SELECT count(*) AS checked,
           count(*) FILTER (
               WHERE s.id IS NULL OR t.id IS NULL OR s.org_id <> e.org_id OR t.org_id <> e.org_id
           ) AS orphaned
    FROM graph_edges e
    LEFT JOIN graph_nodes s ON s.id = e.source_id
    LEFT JOIN graph_nodes t ON t.id = e.target_id
    """
)


async def count_orphaned_edges(session: AsyncSession) -> GraphConsistencyReport:
    row = (await session.execute(_ORPHANS_SQL)).one()
    return GraphConsistencyReport(
        checked_edges=row.checked, orphaned_edges=row.orphaned, checked_at=datetime.now(UTC)
    )


class GraphConsistencyActivities:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @activity.defn
    async def check_graph_consistency(self) -> GraphConsistencyReport:
        async with self._sessions() as session:
            report = await count_orphaned_edges(session)
        log.info(
            "graph_consistency orphaned_edges=%d checked_edges=%d",
            report.orphaned_edges,
            report.checked_edges,
        )
        return report


@workflow.defn
class GraphConsistencyWorkflow:
    @workflow.run
    async def run(self) -> GraphConsistencyReport:
        return await workflow.execute_activity_method(
            GraphConsistencyActivities.check_graph_consistency,
            start_to_close_timeout=timedelta(minutes=10),
        )


async def ensure_nightly_schedule(client: Client, task_queue: str) -> None:
    """Register the nightly run once; restarting the worker keeps the existing schedule."""
    with contextlib.suppress(ScheduleAlreadyRunningError):
        await client.create_schedule(
            SCHEDULE_ID,
            Schedule(
                action=ScheduleActionStartWorkflow(
                    GraphConsistencyWorkflow.run, id=SCHEDULE_ID, task_queue=task_queue
                ),
                spec=ScheduleSpec(cron_expressions=[NIGHTLY_CRON]),
            ),
        )
