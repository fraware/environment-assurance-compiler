#!/usr/bin/env python3
"""Write SHA-256SUMS for release artifacts (GNU coreutils compatible).

Usage:
  python scripts/write_sha256sums.py dist --out dist/SHA-256SUMS
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--glob",
        action="append",
        default=None,
        help="Glob(s) relative to directory (default: *.whl *.tar.gz *.json *.xml)",
    )
    args = parser.parse_args(argv)
    patterns = args.glob or [
        "*.whl",
        "*.tar.gz",
        "*.cdx.json",
        "*.cdx.xml",
        "release-manifest.json",
    ]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(args.directory.glob(pattern)))
    # Unique, stable order; exclude the sums file itself if present.
    uniq = sorted({p.resolve() for p in files if p.is_file() and p.name != "SHA-256SUMS"})
    if not uniq:
        print(f"error: no files matched in {args.directory}", file=sys.stderr)
        return 1
    lines = [f"{_sha256(p)}  {p.name}" for p in uniq]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(lines)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
