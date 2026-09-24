"""Domain events published through the event backbone (ticket S01.3)."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from riven_schemas.domain import ChangeRef, Producer, VerificationStatus


class DomainEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: Literal["1"] = "1"


class ChangeCaptured(DomainEvent):
    type: Literal["change.captured"] = "change.captured"
    change: ChangeRef
    producer: Producer
    files_changed: list[str]


class VerificationCompleted(DomainEvent):
    type: Literal["verification.completed"] = "verification.completed"
    change: ChangeRef
    run_id: str
    status: VerificationStatus
    verifier_identity: str


class BugConfirmed(DomainEvent):
    type: Literal["bug.confirmed"] = "bug.confirmed"
    change: ChangeRef
    bug_id: str
    fingerprint: str
    module: str | None = None
