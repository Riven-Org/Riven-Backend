from riven_schemas import (
    ChangeCaptured,
    ChangeRef,
    Producer,
    ProducerKind,
    VerificationCompleted,
    VerificationStatus,
)

CHANGE = ChangeRef(org_id="org_1", repo="acme/shop", commit_sha="abc123")


def test_change_captured_round_trips_through_json() -> None:
    event = ChangeCaptured(
        change=CHANGE,
        producer=Producer(kind=ProducerKind.AI_AGENT, identity="agent-1", agent_model="x"),
        files_changed=["auth/token.py"],
    )

    restored = ChangeCaptured.model_validate_json(event.model_dump_json())

    assert restored == event
    assert restored.type == "change.captured"


def test_verification_completed_serializes_status_as_string() -> None:
    event = VerificationCompleted(
        change=CHANGE,
        run_id="run_1",
        status=VerificationStatus.NEEDS_REVIEW,
        verifier_identity="riven-verifier",
    )

    assert event.model_dump(mode="json")["status"] == "needs_review"
