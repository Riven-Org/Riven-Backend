"""Shared contracts between Riven services (ticket S01.1).

Every payload that crosses a service boundary is defined here and versioned,
so a change in one service cannot silently break another.
"""

from riven_schemas.domain import (
    BugState,
    ChangeRef,
    LockStatus,
    NodeKind,
    Producer,
    ProducerKind,
    RunState,
    Severity,
    VerificationStage,
    VerificationStatus,
)
from riven_schemas.entities import (
    Bug,
    Change,
    GraphEdge,
    GraphNode,
    RegressionLock,
    StageResult,
    VerdictResult,
    VerificationRun,
)
from riven_schemas.events import (
    BugConfirmed,
    ChangeCaptured,
    DomainEvent,
    LockCreated,
    RegressionDetected,
    VerificationCompleted,
)

SCHEMA_VERSION = "1"

__all__ = [
    "SCHEMA_VERSION",
    "Bug",
    "BugConfirmed",
    "BugState",
    "Change",
    "ChangeCaptured",
    "ChangeRef",
    "DomainEvent",
    "GraphEdge",
    "GraphNode",
    "LockCreated",
    "LockStatus",
    "NodeKind",
    "Producer",
    "ProducerKind",
    "RegressionDetected",
    "RegressionLock",
    "RunState",
    "Severity",
    "StageResult",
    "VerdictResult",
    "VerificationCompleted",
    "VerificationRun",
    "VerificationStage",
    "VerificationStatus",
]
