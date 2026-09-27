"""Contract tests (S01.1.4): CI fails on a backward-incompatible schema change.

Each contract is compared against the committed baseline for the current SCHEMA_VERSION in
packages/schemas/contracts/v<N>/. Additive changes pass. A breaking change must bump
SCHEMA_VERSION and add a new baseline (`uv run python -m riven_schemas.export --snapshot`).
"""

import json
from enum import StrEnum
from pathlib import Path

import pytest
from pydantic import BaseModel

from riven_schemas.compat import breaking_changes
from riven_schemas.contracts import CONTRACTS, json_schemas
from riven_schemas.export import snapshot_dir, write

SNAPSHOT_CMD = "uv run python -m riven_schemas.export --snapshot"


def _baseline(name: str) -> dict[str, object]:
    path = snapshot_dir() / f"{name}.json"
    if not path.exists():
        pytest.fail(f"No baseline for {name}: run `{SNAPSHOT_CMD}`")
    loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_contract_is_backward_compatible_with_baseline(name: str) -> None:
    problems = breaking_changes(_baseline(name), json_schemas()[name])

    assert problems == [], (
        f"{name} has breaking changes; bump SCHEMA_VERSION and add a new baseline:\n"
        + "\n".join(problems)
    )


def test_every_baseline_still_has_a_contract() -> None:
    removed = {p.stem for p in snapshot_dir().glob("*.json")} - set(CONTRACTS)

    assert removed == set(), f"Contracts removed without a schema version bump: {removed}"


def test_export_writes_one_json_schema_per_contract(tmp_path: Path) -> None:
    out = tmp_path
    written = write(out)

    assert {p.stem for p in written} == set(CONTRACTS)
    assert json.loads((out / "Change.json").read_text(encoding="utf-8"))["title"] == "Change"


# --- the checker itself -------------------------------------------------------------------


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class Before(BaseModel):
    name: str
    count: int = 0
    color: Color = Color.RED
    note: str | None = None


def _schema(model: type[BaseModel]) -> dict[str, object]:
    return model.model_json_schema()


def test_adding_an_optional_field_is_compatible() -> None:
    class After(Before):
        extra: str = ""

    assert breaking_changes(_schema(Before), _schema(After)) == []


def test_removing_a_field_is_breaking() -> None:
    class After(BaseModel):
        name: str
        color: Color = Color.RED
        note: str | None = None

    assert breaking_changes(_schema(Before), _schema(After)) == ["$.count: property removed"]


def test_new_required_field_is_breaking() -> None:
    class After(Before):
        owner: str

    assert breaking_changes(_schema(Before), _schema(After)) == [
        "$.owner: property is now required"
    ]


def test_changing_a_field_type_is_breaking() -> None:
    class After(BaseModel):
        name: int
        count: int = 0
        color: Color = Color.RED
        note: str | None = None

    assert breaking_changes(_schema(Before), _schema(After)) == [
        "$.name: type 'string' is no longer accepted"
    ]


def test_making_a_nullable_field_non_nullable_is_breaking() -> None:
    class After(BaseModel):
        name: str
        count: int = 0
        color: Color = Color.RED
        note: str = ""

    assert breaking_changes(_schema(Before), _schema(After)) == [
        "$.note: type 'null' is no longer accepted"
    ]


def test_removing_an_enum_value_is_breaking() -> None:
    class Narrow(StrEnum):
        RED = "red"

    class After(BaseModel):
        name: str
        count: int = 0
        color: Narrow = Narrow.RED
        note: str | None = None

    assert breaking_changes(_schema(Before), _schema(After)) == [
        "$.color: enum values removed: ['blue']"
    ]


def test_changing_an_event_type_constant_is_breaking() -> None:
    from typing import Literal

    class Old(BaseModel):
        type: Literal["bug.confirmed"] = "bug.confirmed"

    class New(BaseModel):
        type: Literal["bug.found"] = "bug.found"

    assert breaking_changes(_schema(Old), _schema(New)) == [
        "$.type: constant changed from 'bug.confirmed' to 'bug.found'"
    ]


def test_every_event_has_a_producer_and_consumers_in_the_catalog() -> None:
    from riven_schemas.catalog import ROUTES
    from riven_schemas.contracts import EVENTS

    assert {e.model_fields["type"].default for e in EVENTS} == set(ROUTES)


def test_event_catalog_doc_is_up_to_date() -> None:
    from riven_schemas.catalog import render

    doc = Path(__file__).resolve().parents[3] / "docs" / "events.md"

    assert doc.read_text(encoding="utf-8") == render(), (
        "docs/events.md is stale: uv run python -m riven_schemas.catalog > docs/events.md"
    )


def test_changing_array_item_type_is_breaking() -> None:
    class OldArray(BaseModel):
        tags: list[str]

    class NewArray(BaseModel):
        tags: list[int]

    assert breaking_changes(_schema(OldArray), _schema(NewArray)) == [
        "$.tags[]: type 'string' is no longer accepted"
    ]


def test_required_story_models_are_registered_as_contracts() -> None:
    """Verify ticket S01.1.3 explicitly required entities and domain events."""
    required_entities = {"Change", "VerificationRun", "Bug", "RegressionLock", "GraphEdge"}
    required_events = {
        "ChangeCaptured",
        "VerificationCompleted",
        "BugConfirmed",
        "RegressionDetected",
        "LockCreated",
    }
    registered = set(CONTRACTS)
    missing = (required_entities | required_events) - registered
    assert missing == set(), f"Required models missing from CONTRACTS registry: {missing}"


def test_every_service_boundary_has_a_merged_adr() -> None:
    """Verify S01.1.1: One ADR per service: responsibility, owned tables, published events."""
    repo_root = Path(__file__).resolve().parents[3]
    adr_dir = repo_root / "docs" / "adr"
    decomp_adr = adr_dir / "0002-service-decomposition.md"

    assert decomp_adr.exists(), "ADR 0002 (service decomposition) must exist"
    decomp_content = decomp_adr.read_text(encoding="utf-8")

    expected_services = [
        ("api-gateway", "0003-service-api-gateway.md"),
        ("capture", "0004-service-capture.md"),
        ("orchestrator", "0005-service-orchestrator.md"),
        ("sandbox-runner", "0006-service-sandbox-runner.md"),
        ("verifier", "0007-service-verifier.md"),
        ("memory", "0008-service-memory.md"),
        ("graph", "0009-service-graph.md"),
        ("web", "0010-service-web.md"),
    ]

    for service_name, adr_filename in expected_services:
        assert service_name in decomp_content, f"ADR 0002 must list service {service_name}"
        service_adr = adr_dir / adr_filename
        assert service_adr.exists(), f"Service ADR {adr_filename} must exist"
        content = service_adr.read_text(encoding="utf-8")
        assert "## Responsibility" in content, f"{adr_filename} must define Responsibility"
        assert "## Runs in" in content, f"{adr_filename} must define Runs in"
        assert "## Owns" in content, f"{adr_filename} must define Owns"
        assert "## Publishes" in content, f"{adr_filename} must define Publishes"
        assert "## Consumes" in content, f"{adr_filename} must define Consumes"
        assert "## Does not" in content, f"{adr_filename} must define Does not"
