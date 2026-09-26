"""S01.4.3: services write logs and artifacts to object storage, never to local disk.

Scans every service's source (apps/*/src) for file-writing calls. If a service genuinely
needs scratch space, it must go through riven_storage instead.
"""

import ast
from pathlib import Path

APPS = Path(__file__).resolve().parents[3] / "apps"
WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "touch"}
DISK_MODULES = {"tempfile", "shutil"}


def _violations(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        where = f"{path}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                modes = [a for a in node.args[1:2]] + [
                    k.value for k in node.keywords if k.arg == "mode"
                ]
                if any(
                    isinstance(m, ast.Constant) and set(str(m.value)) & set("wax+") for m in modes
                ):
                    found.append(f"{where}: open() for writing")
            if isinstance(func, ast.Attribute) and func.attr in WRITE_METHODS:
                found.append(f"{where}: .{func.attr}()")
        if isinstance(node, ast.Import | ast.ImportFrom):
            names = (
                [node.module] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            )
            if any((n or "").split(".")[0] in DISK_MODULES for n in names):
                found.append(f"{where}: imports a local-disk module")
    return found


def test_no_service_writes_to_local_disk() -> None:
    sources = sorted(APPS.glob("*/src/**/*.py"))
    assert sources, "no service sources found"

    violations = [v for path in sources for v in _violations(path)]

    assert violations == [], "Use riven_storage.ObjectStore instead:\n" + "\n".join(violations)


def test_the_scanner_catches_a_local_write(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text("import tempfile\nopen('run.log', 'w').write('x')\nPath('a').write_text('')\n")

    assert len(_violations(probe)) == 3
