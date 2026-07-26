#!/usr/bin/env python3
"""Lint public example-manifest.json files against schemas/example-manifest-1.json.

Uses the stdlib only (no jsonschema dependency). Validates required fields,
enums, and on-disk contract paths for each discovered manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"
SCHEMA_PATH = REPO / "schemas" / "example-manifest-1.json"
ALLOWED_STATUS = frozenset(
    {"scaffold", "contract-complete", "integration-blocked", "release-qualified"}
)
REQUIRED_TOP = (
    "schema_version",
    "id",
    "slug",
    "title",
    "description",
    "status",
    "requires",
    "entrypoints",
    "paths",
)


def _fail(path: Path, message: str) -> None:
    print(f"FAIL {path.as_posix()}: {message}", file=sys.stderr)


def lint_manifest(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot parse JSON: {exc}"]

    if not isinstance(data, dict):
        return ["manifest root must be an object"]

    for key in REQUIRED_TOP:
        if key not in data:
            errors.append(f"missing required field {key!r}")

    if data.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    example_id = data.get("id")
    if isinstance(example_id, str):
        if not (example_id.startswith("E") and example_id[1:].isdigit()):
            errors.append("id must match E<number>")
    elif "id" in data:
        errors.append("id must be a string")

    status = data.get("status")
    if status is not None and status not in ALLOWED_STATUS:
        errors.append(f"status {status!r} not in {sorted(ALLOWED_STATUS)}")

    requires = data.get("requires")
    if isinstance(requires, dict):
        for key in ("python", "envassure", "extras"):
            if key not in requires:
                errors.append(f"requires.{key} missing")
        if "extras" in requires and not isinstance(requires["extras"], list):
            errors.append("requires.extras must be an array")
    elif requires is not None:
        errors.append("requires must be an object")

    entrypoints = data.get("entrypoints")
    root = path.parent
    if isinstance(entrypoints, dict):
        for key in ("run", "verify"):
            if key not in entrypoints:
                errors.append(f"entrypoints.{key} missing")
                continue
            rel = entrypoints[key]
            if not isinstance(rel, str):
                errors.append(f"entrypoints.{key} must be a string")
                continue
            target = root / rel
            if data.get("status") != "scaffold" and not target.is_file():
                errors.append(f"entrypoints.{key} file missing: {rel}")
    elif entrypoints is not None:
        errors.append("entrypoints must be an object")

    paths = data.get("paths")
    if isinstance(paths, dict):
        for key in ("input", "expected"):
            if key not in paths:
                errors.append(f"paths.{key} missing")
                continue
            rel = paths[key]
            if not isinstance(rel, str):
                errors.append(f"paths.{key} must be a string")
                continue
            target = root / rel
            if not target.is_dir():
                errors.append(f"paths.{key} directory missing: {rel}")
    elif paths is not None:
        errors.append("paths must be an object")

    # Scaffold examples may omit full scripts; still require README + manifest.
    if not (root / "README.md").is_file():
        errors.append("README.md missing")

    return errors


def discover_manifests() -> list[Path]:
    if not EXAMPLES.is_dir():
        return []
    return sorted(EXAMPLES.rglob("example-manifest.json"))


def main() -> int:
    if not SCHEMA_PATH.is_file():
        print(f"FAIL schema missing: {SCHEMA_PATH}", file=sys.stderr)
        return 2

    manifests = discover_manifests()
    if not manifests:
        print("FAIL no example-manifest.json files found under examples/", file=sys.stderr)
        return 1

    failed = 0
    for path in manifests:
        errors = lint_manifest(path)
        if errors:
            failed += 1
            for err in errors:
                _fail(path.relative_to(REPO), err)
        else:
            print(f"ok {path.relative_to(REPO).as_posix()}")

    print(f"{len(manifests) - failed}/{len(manifests)} manifests ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
