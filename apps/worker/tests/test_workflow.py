import asyncio
import uuid

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from riven_schemas import ChangeRef, StageResult, VerificationStage, VerificationStatus
from riven_worker.activities import ALL_ACTIVITIES
from riven_worker.workflows import (
    VerificationWorkflow,
    trigger_verification,
)

CHANGE = ChangeRef(org_id="org_1", repo="acme/shop", commit_sha="abc123")


async def test_workflow_runs_every_stage_in_order() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[VerificationWorkflow],
            activities=ALL_ACTIVITIES,
        ):
            result = await env.client.execute_workflow(
                VerificationWorkflow.run, CHANGE, id=str(uuid.uuid4()), task_queue=task_queue
            )

    assert result.status is VerificationStatus.PASSED
    assert [s.stage for s in result.stages] == list(VerificationStage)[1:]


async def test_workflow_short_circuits_on_stage_failure() -> None:
    @activity.defn(name="run_in_sandbox")
    async def failing_sandbox(change: ChangeRef) -> StageResult:
        return StageResult(stage=VerificationStage.SANDBOX, ok=False, detail="tests failed")

    custom_activities = [
        act for act in ALL_ACTIVITIES if getattr(act, "__name__", None) != "run_in_sandbox"
    ] + [failing_sandbox]

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[VerificationWorkflow],
            activities=custom_activities,
        ):
            result = await env.client.execute_workflow(
                VerificationWorkflow.run, CHANGE, id=str(uuid.uuid4()), task_queue=task_queue
            )

    assert result.status is VerificationStatus.FAILED
    assert [s.stage for s in result.stages] == [
        VerificationStage.ANALYZE,
        VerificationStage.SANDBOX,
    ]


async def test_workflow_is_deterministic_on_replay() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        wf_id = str(uuid.uuid4())
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[VerificationWorkflow],
            activities=ALL_ACTIVITIES,
        ):
            await env.client.execute_workflow(
                VerificationWorkflow.run, CHANGE, id=wf_id, task_queue=task_queue
            )
            history = await env.client.get_workflow_handle(wf_id).fetch_history()

        replayer = Replayer(
            workflows=[VerificationWorkflow], data_converter=pydantic_data_converter
        )
        replay_result = await replayer.replay_workflow(history)
        assert replay_result.replay_failure is None


async def test_duplicate_trigger_returns_existing_run_id() -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[VerificationWorkflow],
            activities=ALL_ACTIVITIES,
        ):
            # First trigger starts the workflow
            run_id_1 = await trigger_verification(
                env.client, CHANGE, pipeline_version="v1", task_queue=task_queue
            )
            assert run_id_1 is not None

            # Duplicate trigger for the same commit and version returns existing run_id
            run_id_2 = await trigger_verification(
                env.client, CHANGE, pipeline_version="v1", task_queue=task_queue
            )
            assert run_id_2 == run_id_1

            # Different pipeline version triggers a distinct run
            run_id_v2 = await trigger_verification(
                env.client, CHANGE, pipeline_version="v2", task_queue=task_queue
            )
            assert run_id_v2 != run_id_1


async def test_cancellation_cleans_up_sandbox_resources() -> None:
    sandbox_state = {"allocated": False, "cleaned": False}
    sandbox_started = asyncio.Event()

    @activity.defn(name="run_in_sandbox")
    async def cancellable_sandbox(change: ChangeRef) -> StageResult:
        sandbox_state["allocated"] = True
        sandbox_started.set()
        while True:
            await asyncio.sleep(0.05)
            activity.heartbeat()

    @activity.defn(name="cleanup_sandbox")
    async def spy_cleanup_sandbox(change: ChangeRef) -> StageResult:
        sandbox_state["allocated"] = False
        sandbox_state["cleaned"] = True
        return StageResult(stage=VerificationStage.SANDBOX, ok=True, detail="cleaned up")

    activities = [
        act
        for act in ALL_ACTIVITIES
        if getattr(act, "__name__", None) not in {"run_in_sandbox", "cleanup_sandbox"}
    ] + [cancellable_sandbox, spy_cleanup_sandbox]

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        wf_id = str(uuid.uuid4())
        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[VerificationWorkflow],
            activities=activities,
        ):
            handle = await env.client.start_workflow(
                VerificationWorkflow.run, CHANGE, id=wf_id, task_queue=task_queue
            )
            await sandbox_started.wait()
            assert sandbox_state["allocated"] is True

            # Cancel workflow mid-run
            await handle.cancel()
            with pytest.raises(WorkflowFailureError):
                await handle.result()

            # Prove cleanup activity ran and released sandbox resources
            assert sandbox_state["cleaned"] is True
            assert sandbox_state["allocated"] is False


async def test_worker_interruption_resumes_from_checkpoint() -> None:
    execution_counts = {"analyze_change": 0, "run_in_sandbox": 0}

    @activity.defn(name="analyze_change")
    async def tracking_analyze(change: ChangeRef) -> StageResult:
        execution_counts["analyze_change"] += 1
        return StageResult(stage=VerificationStage.ANALYZE, ok=True)

    @activity.defn(name="run_in_sandbox")
    async def crash_sandbox(change: ChangeRef) -> StageResult:
        execution_counts["run_in_sandbox"] += 1
        if execution_counts["run_in_sandbox"] == 1:
            raise RuntimeError("Simulated worker crash during stage execution")
        return StageResult(stage=VerificationStage.SANDBOX, ok=True)

    activities = [
        act
        for act in ALL_ACTIVITIES
        if getattr(act, "__name__", None) not in {"analyze_change", "run_in_sandbox"}
    ] + [tracking_analyze, crash_sandbox]

    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        task_queue = str(uuid.uuid4())
        wf_id = str(uuid.uuid4())

        async with Worker(
            env.client,
            task_queue=task_queue,
            workflows=[VerificationWorkflow],
            activities=activities,
        ):
            result = await env.client.execute_workflow(
                VerificationWorkflow.run, CHANGE, id=wf_id, task_queue=task_queue
            )

        # Resumed from checkpoint: analyze_change was NOT re-executed!
        assert execution_counts["analyze_change"] == 1
        assert execution_counts["run_in_sandbox"] == 2
        assert result.status is VerificationStatus.PASSED
        assert len(result.stages) == len(list(VerificationStage)[1:])
