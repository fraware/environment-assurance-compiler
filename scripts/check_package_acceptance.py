#!/usr/bin/env python3
"""Package acceptance checks (spec §4.4) — fail-closed.

Verifies for an installed envassure (prefer clean wheel venv):

1. Import isolation — base install must not import optional stacks.
2. pip check — no broken requirements.
3. Package data — schemas exportable; diagnostics catalog non-empty;
   plugin scaffold templates present.
4. project.urls — required keys present in distribution metadata.
5. Optional: sdist↔wheel version equivalence when --dist-dir is given.

Exit 0 on success; 1 on any failure.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN_MODULES = (
    "gymnasium",
    "pettingzoo",
    "psycopg",
    "httpx",
    "openenv",
    "openenv_core",
)

REQUIRED_URL_KEYS = ("Homepage", "Repository", "Issues", "Documentation")

REQUIRED_SCHEMA_NAMES = (
    "world.json",
    "world-0.2.0.json",
    "pack-manifest.json",
    "pack-manifest-2.json",
    "release-manifest-1.json",
)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)


def _ok(msg: str) -> None:
    print(f"ok: {msg}")


def check_import_isolation() -> list[str]:
    errors: list[str] = []
    try:
        import envassure  # noqa: F401
        from envassure import __version__

        _ok(f"import envassure ({__version__})")
    except Exception as exc:
        return [f"base import failed: {exc}"]

    for name in FORBIDDEN_MODULES:
        if name in sys.modules:
            errors.append(f"forbidden module already loaded: {name}")
            continue
        try:
            importlib.import_module(name)
        except ImportError:
            _ok(f"optional stack absent: {name}")
        else:
            errors.append(
                f"base install must not pull optional dependency {name!r} "
                "(import succeeded without extras)"
            )
    return errors


def check_pip() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return [f"pip check failed:\n{proc.stdout}\n{proc.stderr}"]
    _ok("pip check")
    return []


def check_package_data() -> list[str]:
    errors: list[str] = []

    try:
        from envassure.diagnostics.catalog import DIAGNOSTIC_CATALOG
        from envassure.ir.schema import world_json_schema
        from envassure.packaging import pack_schema
        from envassure.plugins import PLUGIN_API_VERSION
    except Exception as exc:
        return [f"package data imports failed: {exc}"]

    if not DIAGNOSTIC_CATALOG:
        errors.append("DIAGNOSTIC_CATALOG is empty")
    else:
        _ok(f"diagnostics catalog entries={len(DIAGNOSTIC_CATALOG)}")

    schema = world_json_schema()
    if not isinstance(schema, dict) or not schema:
        errors.append("world_json_schema() returned empty/invalid")
    else:
        _ok("world_json_schema exportable")

    pschema = pack_schema()
    if not isinstance(pschema, dict) or not pschema:
        errors.append("pack_schema() returned empty/invalid")
    else:
        _ok("pack_schema exportable")

    if not PLUGIN_API_VERSION:
        errors.append("PLUGIN_API_VERSION missing")
    else:
        _ok(f"plugin api {PLUGIN_API_VERSION}")

    # Wheel force-includes schemas/ → envassure/schemas
    try:
        import importlib.resources as resources

        schem_root = resources.files("envassure.schemas")
        for name in ("world.json", "pack-manifest.json", "release-manifest-1.json"):
            target = schem_root.joinpath(name)
            if not target.is_file():
                errors.append(f"wheel package-data missing envassure.schemas/{name}")
            else:
                _ok(f"wheel schema {name}")
    except (TypeError, ModuleNotFoundError, AttributeError) as exc:
        errors.append(f"envassure.schemas package-data not importable: {exc}")

    # Plugin scaffold templates live in plugins.create_plugin_template
    try:
        from envassure.plugins import create_plugin_template

        sample = create_plugin_template("acceptance_probe", kind="generic")
        if not sample or "PLUGIN_API_VERSION" not in sample:
            errors.append("create_plugin_template did not emit expected content")
        else:
            _ok("plugin scaffold template present")
    except Exception as exc:
        errors.append(f"plugin scaffold helper missing: {exc}")

    return errors


def check_project_urls() -> list[str]:
    errors: list[str] = []
    try:
        from importlib import metadata

        meta = metadata.metadata("envassure")
    except Exception as exc:
        return [f"could not read distribution metadata: {exc}"]

    # importlib.metadata exposes Project-URL as multi-value "Label, URL"
    found: dict[str, str] = {}
    for raw in meta.get_all("Project-URL") or []:
        if ", " in raw:
            label, url = raw.split(", ", 1)
            found[label] = url
    for key in REQUIRED_URL_KEYS:
        if key not in found or not found[key].startswith("http"):
            errors.append(f"missing or invalid project.urls entry: {key}")
        else:
            _ok(f"project.urls {key}={found[key]}")
    return errors


def check_repo_schemas(repo_root: Path) -> list[str]:
    errors: list[str] = []
    root = repo_root / "schemas"
    if not root.is_dir():
        return [f"schemas directory missing: {root}"]
    for name in REQUIRED_SCHEMA_NAMES:
        path = root / name
        if not path.is_file():
            errors.append(f"missing published schema: {path}")
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSON schema {path}: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"schema root must be object: {path}")
        else:
            _ok(f"schema {name}")
    return errors


def check_dist_equivalence(dist_dir: Path) -> list[str]:
    errors: list[str] = []
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("envassure-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        return [f"expected one wheel and one sdist in {dist_dir}"]
    wheel_name = wheels[0].name
    sdist_name = sdists[0].name
    # envassure-VERSION-*.whl vs envassure-VERSION.tar.gz
    whl_m = re.match(r"^envassure-(.+?)-py3-none-any\.whl$", wheel_name)
    sdist_m = re.match(r"^envassure-(.+)\.tar\.gz$", sdist_name)
    if not whl_m or not sdist_m:
        return [f"unexpected artifact names: {wheel_name}, {sdist_name}"]
    wheel_ver = whl_m.group(1)
    sdist_ver = sdist_m.group(1)
    try:
        from packaging.version import Version

        equivalent = Version(wheel_ver) == Version(sdist_ver)
    except ImportError:
        equivalent = wheel_ver == sdist_ver
    if not equivalent:
        errors.append(f"wheel/sdist version mismatch: {wheel_ver!r} vs {sdist_ver!r}")
    else:
        _ok(f"wheel/sdist version {wheel_ver}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="If set, also validate checked-in schemas/ files.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=None,
        help="If set, verify wheel/sdist version equivalence.",
    )
    parser.add_argument(
        "--skip-isolation",
        action="store_true",
        help="Skip optional-stack isolation (e.g. when extras are installed).",
    )
    args = parser.parse_args(argv)

    errors: list[str] = []
    if not args.skip_isolation:
        errors.extend(check_import_isolation())
    else:
        _ok("skipped import isolation")
    errors.extend(check_pip())
    errors.extend(check_package_data())
    errors.extend(check_project_urls())
    if args.repo_root is not None:
        errors.extend(check_repo_schemas(args.repo_root))
    if args.dist_dir is not None:
        errors.extend(check_dist_equivalence(args.dist_dir))

    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("package acceptance: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
