import uuid

from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from riven_schemas import ChangeRef, VerificationStage, VerificationStatus
from riven_worker.activities import ALL_ACTIVITIES
from riven_worker.workflows import VerificationWorkflow


async def test_workflow_runs_every_stage_in_order() -> None:
    change = ChangeRef(org_id="org_1", repo="acme/shop", commit_sha="abc123")
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
                VerificationWorkflow.run, change, id=str(uuid.uuid4()), task_queue=task_queue
            )

    assert result.status is VerificationStatus.PASSED
    assert [s.stage for s in result.stages] == list(VerificationStage)[1:]
