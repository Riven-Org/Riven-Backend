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
    loaded: dict[str, object] = json.loads(path.read_text())
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
    assert json.loads((out / "Change.json").read_text())["title"] == "Change"


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

    assert doc.read_text() == render(), (
        "docs/events.md is stale: uv run python -m riven_schemas.catalog > docs/events.md"
    )
