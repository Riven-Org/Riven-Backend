"""Shared contracts between Riven services (ticket S01.1).

Every payload that crosses a service boundary is defined here and versioned,
so a change in one service cannot silently break another.
"""

from riven_schemas.domain import (
    BugState,
    ChangeRef,
    Producer,
    ProducerKind,
    VerificationStage,
    VerificationStatus,
)
from riven_schemas.events import (
    BugConfirmed,
    ChangeCaptured,
    DomainEvent,
    VerificationCompleted,
)

SCHEMA_VERSION = "1"

__all__ = [
    "SCHEMA_VERSION",
    "BugConfirmed",
    "BugState",
    "ChangeCaptured",
    "ChangeRef",
    "DomainEvent",
    "Producer",
    "ProducerKind",
    "VerificationCompleted",
    "VerificationStage",
    "VerificationStatus",
]
