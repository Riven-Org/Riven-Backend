from riven_schemas import ChangeRef, VerificationStage
from riven_worker.activities import ALL_ACTIVITIES, analyze_change
from riven_worker.workflows import workflow_id_for

CHANGE = ChangeRef(org_id="org_1", repo="acme/shop", commit_sha="abc123")


async def test_analyze_change_returns_its_stage() -> None:
    result = await analyze_change(CHANGE)

    assert result.stage is VerificationStage.ANALYZE


def test_every_pipeline_stage_after_capture_has_an_activity() -> None:
    assert len(ALL_ACTIVITIES) == len(VerificationStage) - 1


def test_workflow_id_is_stable_per_commit() -> None:
    assert workflow_id_for(CHANGE) == workflow_id_for(CHANGE.model_copy())
    assert workflow_id_for(CHANGE) != workflow_id_for(CHANGE.model_copy(update={"commit_sha": "x"}))
