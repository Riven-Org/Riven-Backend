"""Core entities shared between services (ticket S01.1.3).

These are the read/transfer shapes of each service's owned data (see docs/adr/0002). Services
keep their own storage models; anything that crosses a boundary uses these.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from riven_schemas.domain import (
    BugState,
    ChangeRef,
    LockStatus,
    NodeKind,
    Producer,
    RunState,
    Severity,
    VerificationStage,
    VerificationStatus,
)


class Change(BaseModel):
    """A captured commit or PR and who produced it (capture service)."""

    model_config = ConfigDict(frozen=True)

    ref: ChangeRef
    producer: Producer
    title: str = ""
    branch: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    captured_at: datetime


class StageResult(BaseModel):
    """Outcome of one pipeline stage (Temporal activity result)."""

    stage: VerificationStage
    ok: bool
    detail: str = ""


class VerdictResult(BaseModel):
    """Result of a whole verification workflow run."""

    status: VerificationStatus
    stages: list[StageResult]


class VerificationRun(BaseModel):
    """One verification of one change (orchestrator service)."""

    id: str
    change: ChangeRef
    state: RunState
    verdict: VerificationStatus | None = None
    verifier_identity: str
    stages: list[StageResult] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None


class Bug(BaseModel):
    """A remembered bug, recognised across runs by its fingerprint (memory service)."""

    id: str
    org_id: str
    repo: str
    fingerprint: str
    title: str
    state: BugState
    severity: Severity
    module: str | None = None
    first_seen: ChangeRef
    occurrences: int = 1


class RegressionLock(BaseModel):
    """A test that fails on the buggy commit and passes on the fix (memory service)."""

    id: str
    org_id: str
    bug_id: str
    test_ref: str
    fixed_by: ChangeRef
    status: LockStatus = LockStatus.ACTIVE


class GraphNode(BaseModel):
    """A causal graph node (graph service)."""

    id: str
    org_id: str
    kind: NodeKind
    key: str
    label: str = ""
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A causal graph edge. Edges carry provenance and are closed, never deleted."""

    id: str
    org_id: str
    kind: str
    source_id: str
    target_id: str
    provenance: str
    confidence: float = Field(ge=0.0, le=1.0)
    created_by: str
    valid_from: datetime
    valid_to: datetime | None = None


class GraphConsistencyReport(BaseModel):
    """Result of the nightly graph consistency check (S01.4.4)."""

    checked_edges: int
    orphaned_edges: int
    checked_at: datetime
