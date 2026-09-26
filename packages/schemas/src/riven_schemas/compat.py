"""Backward-compatibility check between two JSON Schemas of the same contract (S01.1.4).

A change is breaking when data valid under the old schema, or code written against it, stops
working: a property is removed, a new property becomes required, a type is narrowed, an enum
value is removed or a constant changes. Adding optional properties or enum values is safe.
"""

from typing import Any

Schema = dict[str, Any]


def breaking_changes(old: Schema, new: Schema) -> list[str]:
    """Return one human-readable line per breaking change; empty means compatible."""
    problems: list[str] = []
    _compare(old, new, old, new, "$", problems)
    return problems


def _resolve(schema: Schema, root: Schema) -> Schema:
    while "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        schema = root.get("$defs", {})[name]
    return schema


def _variants(schema: Schema, root: Schema) -> list[Schema]:
    schema = _resolve(schema, root)
    options = schema.get("anyOf") or schema.get("oneOf")
    if options is None:
        return [schema]
    return [v for option in options for v in _variants(option, root)]


def _kind(schema: Schema) -> str:
    if "const" in schema:
        return "const"
    kind = schema.get("type", "any")
    return kind if isinstance(kind, str) else "|".join(sorted(kind))


def _compare(
    old: Schema, new: Schema, old_root: Schema, new_root: Schema, path: str, problems: list[str]
) -> None:
    old_variants = _variants(old, old_root)
    new_variants = _variants(new, new_root)
    if any(_kind(v) == "any" for v in new_variants):
        return
    for o in old_variants:
        match = next((n for n in new_variants if _kind(n) == _kind(o)), None)
        if match is None:
            problems.append(f"{path}: type '{_kind(o)}' is no longer accepted")
            continue
        _compare_same_kind(o, match, old_root, new_root, path, problems)


def _compare_same_kind(
    o: Schema, n: Schema, old_root: Schema, new_root: Schema, path: str, problems: list[str]
) -> None:
    if "const" in o and o["const"] != n.get("const"):
        problems.append(f"{path}: constant changed from {o['const']!r} to {n.get('const')!r}")
    if "enum" in o:
        removed = set(o["enum"]) - set(n.get("enum") or o["enum"])
        if removed:
            problems.append(f"{path}: enum values removed: {sorted(map(str, removed))}")
    if o.get("type") == "object":
        old_props: Schema = o.get("properties", {})
        new_props: Schema = n.get("properties", {})
        for name, old_prop in old_props.items():
            if name not in new_props:
                problems.append(f"{path}.{name}: property removed")
            else:
                _compare(old_prop, new_props[name], old_root, new_root, f"{path}.{name}", problems)
        newly_required = set(n.get("required", [])) - set(o.get("required", []))
        for name in sorted(newly_required):
            problems.append(f"{path}.{name}: property is now required")
    if o.get("type") == "array" and "items" in o and "items" in n:
        _compare(o["items"], n["items"], old_root, new_root, f"{path}[]", problems)
