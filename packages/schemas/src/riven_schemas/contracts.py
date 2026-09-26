"""Registry of every cross-service contract, exported as JSON Schema (ticket S01.1.3).

Adding a model that crosses a service boundary means adding it here; the contract tests then
guard it against breaking changes.
"""

from typing import Any

from pydantic import BaseModel

from riven_schemas.domain import ChangeRef, Producer
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

EVENTS: tuple[type[DomainEvent], ...] = (
    ChangeCaptured,
    VerificationCompleted,
    BugConfirmed,
    RegressionDetected,
    LockCreated,
)

_MODELS: tuple[type[BaseModel], ...] = (
    ChangeRef,
    Producer,
    Change,
    StageResult,
    VerdictResult,
    VerificationRun,
    Bug,
    RegressionLock,
    GraphNode,
    GraphEdge,
    *EVENTS,
)

CONTRACTS: dict[str, type[BaseModel]] = {model.__name__: model for model in _MODELS}


def json_schemas() -> dict[str, dict[str, Any]]:
    """JSON Schema of every contract, keyed by model name."""
    return {name: model.model_json_schema() for name, model in CONTRACTS.items()}
