from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from riven_schemas import ChangeRef, VerificationStatus
    from riven_worker.activities import (
        StageResult,
        VerdictResult,
        analyze_change,
        run_in_sandbox,
        update_graph,
        update_memory,
        verify,
    )

STAGE_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2))


def workflow_id_for(change: ChangeRef) -> str:
    """One run per (repo, commit): a re-delivered webhook reuses the same workflow (S01.2.3)."""
    return f"verify:{change.org_id}:{change.repo}:{change.commit_sha}"


@workflow.defn
class VerificationWorkflow:
    """Capture → Analyze → Sandbox → Verify → Memory → Graph (MVP flow)."""

    @workflow.run
    async def run(self, change: ChangeRef) -> VerdictResult:
        stages: list[StageResult] = []
        for step, timeout in (
            (analyze_change, timedelta(minutes=2)),
            (run_in_sandbox, timedelta(minutes=30)),
            (verify, timedelta(minutes=10)),
            (update_memory, timedelta(minutes=2)),
            (update_graph, timedelta(minutes=2)),
        ):
            result = await workflow.execute_activity(
                step, change, start_to_close_timeout=timeout, retry_policy=STAGE_RETRY
            )
            stages.append(result)
            if not result.ok:
                return VerdictResult(status=VerificationStatus.FAILED, stages=stages)
        return VerdictResult(status=VerificationStatus.PASSED, stages=stages)
