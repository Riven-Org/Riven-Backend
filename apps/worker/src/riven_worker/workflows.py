import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, CancelledError, WorkflowAlreadyStartedError

with workflow.unsafe.imports_passed_through():
    from riven_schemas import (
        ChangeRef,
        StageResult,
        VerdictResult,
        VerificationStage,
        VerificationStatus,
    )
    from riven_worker.activities import (
        analyze_change,
        cleanup_sandbox,
        run_in_sandbox,
        update_graph,
        update_memory,
        verify,
    )

DEFAULT_PIPELINE_VERSION = "v1"


@dataclass(frozen=True)
class ActivityPolicy:
    """Explicit timeout, heartbeat, and retry configuration for a pipeline activity (S01.2.4)."""

    start_to_close_timeout: timedelta
    retry_policy: RetryPolicy
    heartbeat_timeout: timedelta | None = None


STAGE_POLICIES: dict[VerificationStage, ActivityPolicy] = {
    VerificationStage.ANALYZE: ActivityPolicy(
        start_to_close_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2)),
    ),
    VerificationStage.SANDBOX: ActivityPolicy(
        start_to_close_timeout=timedelta(minutes=30),
        retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=5)),
        heartbeat_timeout=timedelta(minutes=1),
    ),
    VerificationStage.VERIFY: ActivityPolicy(
        start_to_close_timeout=timedelta(minutes=10),
        retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2)),
    ),
    VerificationStage.MEMORY: ActivityPolicy(
        start_to_close_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2)),
    ),
    VerificationStage.GRAPH: ActivityPolicy(
        start_to_close_timeout=timedelta(minutes=2),
        retry_policy=RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=2)),
    ),
}

CLEANUP_POLICY = ActivityPolicy(
    start_to_close_timeout=timedelta(minutes=5),
    retry_policy=RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=2)),
)

STAGE_SEQUENCE = (
    (analyze_change, VerificationStage.ANALYZE),
    (run_in_sandbox, VerificationStage.SANDBOX),
    (verify, VerificationStage.VERIFY),
    (update_memory, VerificationStage.MEMORY),
    (update_graph, VerificationStage.GRAPH),
)


def workflow_id_for(change: ChangeRef, pipeline_version: str = DEFAULT_PIPELINE_VERSION) -> str:
    """One run per (org, repo, commit, pipeline_version).

    A re-delivered webhook reuses the same workflow (S01.2.3).
    """
    return f"verify:{change.org_id}:{change.repo}:{change.commit_sha}:{pipeline_version}"


async def trigger_verification(
    client: Client,
    change: ChangeRef,
    pipeline_version: str = DEFAULT_PIPELINE_VERSION,
    task_queue: str = "verification",
) -> str:
    """Trigger a verification workflow run with idempotency (ticket S01.2.3).

    Returns the new or existing workflow run ID. A re-delivered trigger for the same commit
    and pipeline version does not create a duplicate execution.
    """
    workflow_id = workflow_id_for(change, pipeline_version)
    try:
        handle = await client.start_workflow(
            VerificationWorkflow.run,
            change,
            id=workflow_id,
            task_queue=task_queue,
        )
        return handle.result_run_id or handle.first_execution_run_id or handle.id
    except WorkflowAlreadyStartedError as exc:
        if exc.run_id:
            return exc.run_id
        existing_handle = client.get_workflow_handle(workflow_id)
        desc = await existing_handle.describe()
        return desc.run_id


@workflow.defn
class VerificationWorkflow:
    """Capture → Analyze → Sandbox → Verify → Memory → Graph (MVP flow).

    Durable workflow orchestration: retriable activities, explicit timeouts,
    deterministic execution, worker crash recovery, and cancellation cleanup.
    """

    @workflow.run
    async def run(self, change: ChangeRef) -> VerdictResult:
        stages: list[StageResult] = []
        try:
            for step, stage_enum in STAGE_SEQUENCE:
                policy = STAGE_POLICIES[stage_enum]
                result = await workflow.execute_activity(
                    step,
                    change,
                    start_to_close_timeout=policy.start_to_close_timeout,
                    retry_policy=policy.retry_policy,
                    heartbeat_timeout=policy.heartbeat_timeout,
                )
                stages.append(result)
                if not result.ok:
                    return VerdictResult(status=VerificationStatus.FAILED, stages=stages)
            return VerdictResult(status=VerificationStatus.PASSED, stages=stages)
        except (asyncio.CancelledError, ActivityError) as exc:
            is_cancelled = isinstance(exc, asyncio.CancelledError) or (
                isinstance(exc, ActivityError) and isinstance(exc.cause, CancelledError)
            )
            if is_cancelled:
                # S01.2.4: cancellation tears down sandbox resources
                await asyncio.shield(
                    workflow.execute_activity(
                        cleanup_sandbox,
                        change,
                        start_to_close_timeout=CLEANUP_POLICY.start_to_close_timeout,
                        retry_policy=CLEANUP_POLICY.retry_policy,
                    )
                )
            raise
