"""Write every contract's JSON Schema to a directory (S01.1.3).

uv run python -m riven_schemas.export build/json-schema          # CI artifact
uv run python -m riven_schemas.export --snapshot                 # refresh contract baseline
"""

import argparse
import json
from pathlib import Path

from riven_schemas import SCHEMA_VERSION
from riven_schemas.contracts import json_schemas

SNAPSHOT_ROOT = Path(__file__).resolve().parents[2] / "contracts"


def snapshot_dir(version: str = SCHEMA_VERSION) -> Path:
    """Committed baseline of the contracts for one schema version."""
    return SNAPSHOT_ROOT / f"v{version}"


def write(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, schema in sorted(json_schemas().items()):
        path = out / f"{name}.json"
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", nargs="?", type=Path, help="output directory")
    parser.add_argument("--snapshot", action="store_true", help="write the committed baseline")
    args = parser.parse_args()
    if not args.snapshot and args.out is None:
        parser.error("give an output directory or --snapshot")
    out = snapshot_dir() if args.snapshot else args.out
    for path in write(out):
        print(path)


if __name__ == "__main__":
    main()
