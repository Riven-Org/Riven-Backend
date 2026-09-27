"""S03.2.3 lint rule: raw graph SQL or graph models outside the repository module fail CI.

Graph queries must go through riven_db.graph_repository so they are always org-scoped.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ALLOWED = {
    "packages/db/src/riven_db/graph_repository.py",
    "packages/db/src/riven_db/models/graph.py",
    "packages/db/src/riven_db/models/__init__.py",
}
FORBIDDEN = re.compile(r"\bgraph_(nodes|edges)\b|\bGraph(Node|Edge)\b(?!\w)")


def _offenders(files: list[Path]) -> list[str]:
    found = []
    for path in files:
        rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        if rel in ALLOWED:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if FORBIDDEN.search(code) and "riven_schemas" not in code:
                found.append(f"{rel}:{number}: {line.strip()}")
    return found


def test_graph_tables_are_only_touched_by_the_repository() -> None:
    sources = sorted(ROOT.glob("apps/*/src/**/*.py")) + sorted(ROOT.glob("packages/*/src/**/*.py"))
    sources = [p for p in sources if "riven_schemas" not in p.parts]

    offenders = _offenders(sources)

    assert offenders == [], "Use riven_db.graph_repository.GraphRepository:\n" + "\n".join(
        offenders
    )


def test_the_rule_catches_raw_graph_sql(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text('QUERY = "SELECT * FROM graph_edges"\nfrom x import GraphNode\n')

    assert len(_offenders([probe])) == 2
