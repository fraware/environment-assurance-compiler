#!/usr/bin/env python3
"""Generate schemas/release-manifest-1.json-conformant release-manifest.json.

Fail-closed: refuses to emit a manifest without wheel+sdist digests, tag,
commit, and a non-empty known_limitations list.

Example:
  python scripts/generate_release_manifest.py \\
    --dist-dir dist \\
    --tag v0.2.0.dev0 \\
    --commit \"$(git rev-parse HEAD)\" \\
    --out dist/release-manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA_PATH = _ROOT / "schemas" / "release-manifest-1.json"

_DEFAULT_LIMITATIONS = [
    "Public beta foundation: reference integrations (OpenEnv, OPA, Gymnasium "
    "conformance, HTTP+PG differential) may be unfinished on this train until "
    "Milestone C qualifies them.",
    "PettingZoo adapter remains experimental; no conformance claim.",
    "PyPI trusted publishing and name claim are maintainer-operated; see "
    "docs/contributing/release-process.md.",
]


def _sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _file_digest(path: Path, *, relative_to: Path | None = None) -> dict[str, Any]:
    digest, size = _sha256_file(path)
    rel = (
        path.name if relative_to is None else str(path.relative_to(relative_to)).replace("\\", "/")
    )
    return {"path": rel, "sha256": digest, "size": size}


def _read_version() -> str:
    text = (_ROOT / "src" / "envassure" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise SystemExit("could not parse __version__")
    return match.group(1)


def _read_ir_and_plugin() -> tuple[str, str]:
    # Lightweight parse to avoid importing the full package (release isolation).
    ir_text = (_ROOT / "src" / "envassure" / "ir" / "primitives.py").read_text(encoding="utf-8")
    ir_m = re.search(r'^IR_VERSION\s*=\s*["\']([^"\']+)["\']', ir_text, re.MULTILINE)
    if not ir_m:
        raise SystemExit("could not parse IR_VERSION")
    plug_text = (_ROOT / "src" / "envassure" / "plugins" / "__init__.py").read_text(
        encoding="utf-8"
    )
    plug_m = re.search(r'^PLUGIN_API_VERSION\s*=\s*["\']([^"\']+)["\']', plug_text, re.MULTILINE)
    if not plug_m:
        raise SystemExit("could not parse PLUGIN_API_VERSION")
    return ir_m.group(1), plug_m.group(1)


def _read_requires_python() -> str:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise SystemExit("could not parse requires-python")
    return match.group(1)


def _read_project_urls() -> dict[str, str]:
    text = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    # Minimal TOML table parse for [project.urls] string values only.
    urls: dict[str, str] = {}
    in_urls = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_urls = stripped == "[project.urls]"
            continue
        if not in_urls or not stripped or stripped.startswith("#"):
            continue
        m = re.match(r'^([A-Za-z0-9_-]+)\s*=\s*["\']([^"\']+)["\']', stripped)
        if m:
            urls[m.group(1)] = m.group(2)
    if not urls:
        raise SystemExit("could not parse [project.urls]")
    return urls


def _find_one(dist_dir: Path, pattern: str) -> Path:
    matches = sorted(dist_dir.glob(pattern))
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one {pattern} in {dist_dir}, found {len(matches)}")
    return matches[0]


def _optional_digest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    return _file_digest(path)


def build_manifest(
    *,
    dist_dir: Path,
    tag: str,
    commit: str,
    docs_version: str | None,
    container: dict[str, Any] | None,
    integrations: dict[str, Any] | None,
    packs: list[dict[str, Any]] | None,
    limitations: list[str],
    release_version: str | None,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise SystemExit(f"commit must be a 40-char lowercase hex SHA, got {commit!r}")
    if not tag.startswith("v"):
        raise SystemExit(f"tag must start with 'v', got {tag!r}")
    version = release_version or _read_version()
    tag_version = tag[1:]
    if tag_version != version:
        raise SystemExit(f"tag {tag!r} does not match release_version {version!r}")
    if not limitations:
        raise SystemExit("known_limitations must be non-empty (fail-closed)")

    wheel = _find_one(dist_dir, "*.whl")
    sdist = _find_one(dist_dir, "*.tar.gz")
    ir_version, plugin_api = _read_ir_and_plugin()

    artifacts: dict[str, Any] = {
        "wheel": _file_digest(wheel),
        "sdist": _file_digest(sdist),
        "sbom_cdx_json": _optional_digest(dist_dir / "envassure.cdx.json"),
        "sbom_cdx_xml": _optional_digest(dist_dir / "envassure.cdx.xml"),
        "sha256sums": _optional_digest(dist_dir / "SHA-256SUMS"),
        "repro_bundle": _optional_digest(dist_dir / "repro-bundle.tar.gz"),
    }
    # Drop nulls for cleaner JSON while keeping required wheel/sdist.
    artifacts = {k: v for k, v in artifacts.items() if v is not None or k in {"wheel", "sdist"}}
    # Ensure required keys always present
    artifacts["wheel"] = _file_digest(wheel)
    artifacts["sdist"] = _file_digest(sdist)

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "project": "envassure",
        "release_version": version,
        "tag": tag,
        "commit": commit,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "python": {
            "requires": _read_requires_python(),
            "build": platform.python_version(),
        },
        "ir_version": ir_version,
        "plugin_api_version": plugin_api,
        "docs_version": docs_version,
        "artifacts": artifacts,
        "container": container,
        "integrations": integrations
        or {
            "gymnasium": {
                "status": "scaffold",
                "extra": "gym",
                "upstream_pin": None,
                "notes": None,
            },
            "openenv": {
                "status": "absent",
                "extra": "openenv",
                "upstream_pin": None,
                "notes": None,
            },
            "opa": {"status": "absent", "extra": "opa", "upstream_pin": None, "notes": None},
            "differential_http_pg": {
                "status": "absent",
                "extra": "postgres",
                "upstream_pin": None,
                "notes": None,
            },
            "pettingzoo": {
                "status": "experimental",
                "extra": "pettingzoo",
                "upstream_pin": None,
                "notes": "Not release-qualified.",
            },
        },
        "packs": packs or [],
        "project_urls": _read_project_urls(),
        "known_limitations": limitations,
    }
    return manifest


def _validate_against_schema(manifest: dict[str, Any]) -> None:
    """Structural validation without jsonschema dependency (fail-closed subset)."""
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    required = schema.get("required", [])
    for key in required:
        if key not in manifest:
            raise SystemExit(f"manifest missing required key {key!r}")
    if manifest.get("schema_version") != 1:
        raise SystemExit("schema_version must be 1")
    if manifest.get("project") != "envassure":
        raise SystemExit("project must be envassure")
    arts = manifest.get("artifacts") or {}
    for key in ("wheel", "sdist"):
        if key not in arts or not isinstance(arts[key], dict):
            raise SystemExit(f"artifacts.{key} required")
        for field in ("path", "sha256", "size"):
            if field not in arts[key]:
                raise SystemExit(f"artifacts.{key}.{field} required")
        if not re.fullmatch(r"[0-9a-f]{64}", arts[key]["sha256"]):
            raise SystemExit(f"artifacts.{key}.sha256 invalid")
    if not manifest.get("known_limitations"):
        raise SystemExit("known_limitations must be non-empty")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=_ROOT / "dist")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--docs-version", default=None)
    parser.add_argument(
        "--container-json",
        default=None,
        help="Path to JSON object for container coordinates, or omit for null.",
    )
    parser.add_argument(
        "--limitations-file",
        type=Path,
        default=None,
        help="Optional UTF-8 file with one limitation per line (non-empty lines).",
    )
    parser.add_argument("--release-version", default=None)
    args = parser.parse_args(argv)

    limitations = list(_DEFAULT_LIMITATIONS)
    if args.limitations_file is not None:
        lines = [
            ln.strip()
            for ln in args.limitations_file.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if not lines:
            print("error: limitations file produced no entries", file=sys.stderr)
            return 1
        limitations = lines

    container = None
    if args.container_json:
        container = json.loads(Path(args.container_json).read_text(encoding="utf-8"))

    try:
        manifest = build_manifest(
            dist_dir=args.dist_dir,
            tag=args.tag,
            commit=args.commit.lower(),
            docs_version=args.docs_version,
            container=container,
            integrations=None,
            packs=None,
            limitations=limitations,
            release_version=args.release_version,
        )
        _validate_against_schema(manifest)
    except SystemExit as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out = args.out or (args.dist_dir / "release-manifest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
