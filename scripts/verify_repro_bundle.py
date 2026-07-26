#!/usr/bin/env python3
"""Verify a reproducibility bundle directory against MANIFEST / expected digests.

Fail-closed: any missing file or digest mismatch exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "bundle_dir",
        type=Path,
        nargs="?",
        default=Path("."),
        help="Bundle root containing MANIFEST.json and expected/digests.json",
    )
    args = parser.parse_args(argv)
    root = args.bundle_dir
    manifest_path = root / "MANIFEST.json"
    expected_path = root / "expected" / "digests.json"
    if not manifest_path.is_file():
        print(f"error: missing {manifest_path}", file=sys.stderr)
        return 1
    if not expected_path.is_file():
        print(f"error: missing {expected_path}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    if not isinstance(expected, dict) or not expected:
        print("error: expected digests must be a non-empty object", file=sys.stderr)
        return 1
    errors: list[str] = []
    for path, digest in expected.items():
        p = root / path
        if not p.is_file():
            errors.append(f"missing {path}")
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != digest:
            errors.append(f"digest mismatch {path}: expected {digest}, got {got}")
    # Manifest files list must agree with expected keys when present
    files = manifest.get("files")
    if isinstance(files, list):
        for entry in files:
            if not isinstance(entry, dict):
                continue
            rel = entry.get("path")
            if rel and rel not in expected:
                errors.append(f"manifest file not in expected digests: {rel}")
    if errors:
        print("FAIL:", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print(f"repro verify ok: {len(expected)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
