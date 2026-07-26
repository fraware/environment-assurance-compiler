#!/usr/bin/env python3
"""Fail-closed gate: git tag / GITHUB_REF_NAME must match package __version__.

Usage:
  python scripts/check_tag_version.py
  python scripts/check_tag_version.py --tag v0.2.0b1
  python scripts/check_tag_version.py --version 0.2.0b1 --tag v0.2.0b1

Exit codes:
  0 — match
  1 — mismatch or missing required inputs
  2 — usage / unexpected error
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_TAG_RE = re.compile(r"^v(?P<version>.+)$")
_ROOT = Path(__file__).resolve().parents[1]


def _read_package_version() -> str:
    init_path = _ROOT / "src" / "envassure" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise SystemExit(f"could not parse __version__ from {init_path}")
    return match.group(1)


def _normalize_tag(tag: str) -> str:
    tag = tag.strip()
    if tag.startswith("refs/tags/"):
        tag = tag[len("refs/tags/") :]
    return tag


def version_from_tag(tag: str) -> str:
    """Map ``v1.2.3`` / ``refs/tags/v1.2.3`` → ``1.2.3``. Fail closed otherwise."""
    normalized = _normalize_tag(tag)
    match = _TAG_RE.match(normalized)
    if not match:
        raise ValueError(
            f"tag {tag!r} must be an annotated release tag of the form 'v<pep440-version>'"
        )
    return match.group("version")


def resolve_tag(explicit: str | None) -> str | None:
    if explicit:
        return _normalize_tag(explicit)
    ref = os.environ.get("GITHUB_REF", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    if ref_type == "tag" and ref_name:
        return _normalize_tag(ref_name)
    if ref.startswith("refs/tags/"):
        return _normalize_tag(ref)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default=None,
        help="Git tag (v*). Defaults to GITHUB_REF_NAME / GITHUB_REF when set.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Expected package version. Defaults to src/envassure/__init__.py.",
    )
    parser.add_argument(
        "--allow-untagged",
        action="store_true",
        help="Exit 0 when no tag is available (local/dev). Release CI must omit this.",
    )
    args = parser.parse_args(argv)

    try:
        package_version = args.version or _read_package_version()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    tag = resolve_tag(args.tag)
    if tag is None:
        if args.allow_untagged:
            print(f"no tag in environment; package version={package_version} (allowed)")
            return 0
        print(
            "error: no release tag provided (pass --tag or set GITHUB_REF_TYPE=tag). "
            "Refusing to proceed (fail-closed).",
            file=sys.stderr,
        )
        return 1

    try:
        tag_version = version_from_tag(tag)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if tag_version != package_version:
        print(
            f"error: tag/version mismatch: tag={tag!r} → {tag_version!r}, "
            f"package __version__={package_version!r}",
            file=sys.stderr,
        )
        return 1

    print(f"ok: tag {tag} matches package version {package_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
