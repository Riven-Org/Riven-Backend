from datetime import timedelta

from riven_schemas import ChangeRef, VerificationStage
from riven_worker.activities import (
    ALL_ACTIVITIES,
    STAGE_ACTIVITIES,
    analyze_change,
    cleanup_sandbox,
)
from riven_worker.workflows import (
    CLEANUP_POLICY,
    STAGE_POLICIES,
    STAGE_SEQUENCE,
    workflow_id_for,
)

CHANGE = ChangeRef(org_id="org_1", repo="acme/shop", commit_sha="abc123")


async def test_analyze_change_returns_its_stage() -> None:
    result = await analyze_change(CHANGE)

    assert result.stage is VerificationStage.ANALYZE
    assert result.ok is True


async def test_cleanup_sandbox_returns_success() -> None:
    result = await cleanup_sandbox(CHANGE)

    assert result.stage is VerificationStage.SANDBOX
    assert result.ok is True
    assert "cleaned up" in result.detail


def test_every_pipeline_stage_after_capture_has_an_activity() -> None:
    assert len(STAGE_ACTIVITIES) == len(VerificationStage) - 1
    assert set(STAGE_ACTIVITIES).issubset(set(ALL_ACTIVITIES))
    assert cleanup_sandbox in ALL_ACTIVITIES


def test_every_pipeline_stage_has_explicit_timeout_and_retries() -> None:
    for _, stage_enum in STAGE_SEQUENCE:
        policy = STAGE_POLICIES[stage_enum]
        assert policy.start_to_close_timeout > timedelta(0)
        assert policy.retry_policy is not None
        assert policy.retry_policy.maximum_attempts >= 3

    assert CLEANUP_POLICY.start_to_close_timeout > timedelta(0)
    assert CLEANUP_POLICY.retry_policy is not None


def test_workflow_id_is_stable_per_commit() -> None:
    assert workflow_id_for(CHANGE) == workflow_id_for(CHANGE.model_copy())
    assert workflow_id_for(CHANGE) != workflow_id_for(CHANGE.model_copy(update={"commit_sha": "x"}))


def test_workflow_id_varies_by_pipeline_version() -> None:
    assert workflow_id_for(CHANGE, "v1") != workflow_id_for(CHANGE, "v2")
    assert "v2" in workflow_id_for(CHANGE, "v2")
