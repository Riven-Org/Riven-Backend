"""Registry of every cross-service contract, exported as JSON Schema (ticket S01.1.3).

Adding a model that crosses a service boundary means adding it here; the contract tests then
guard it against breaking changes.
"""

from typing import Annotated, Any, Union

from pydantic import BaseModel, Field, TypeAdapter

from riven_schemas.domain import ChangeRef, Producer
from riven_schemas.entities import (
    Bug,
    Change,
    GraphConsistencyReport,
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
    GraphConsistencyReport,
    *EVENTS,
)

CONTRACTS: dict[str, type[BaseModel]] = {model.__name__: model for model in _MODELS}


def json_schemas() -> dict[str, dict[str, Any]]:
    """JSON Schema of every contract, keyed by model name."""
    return {name: model.model_json_schema() for name, model in CONTRACTS.items()}


_EVENT_ADAPTER: TypeAdapter[DomainEvent] = TypeAdapter(
    Annotated[Union[*EVENTS], Field(discriminator="type")]  # noqa: UP007
)


def parse_event(data: str | bytes) -> DomainEvent:
    """Decode an event from its JSON form into the concrete event class."""
    return _EVENT_ADAPTER.validate_json(data)
