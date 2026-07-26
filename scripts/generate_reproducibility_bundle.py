"""Assemble / refresh the checked-in reproducibility bundle digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "reproducibility"
PACKS = ROOT / "packs"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_commit() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        )
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return "UNKNOWN"


def _collect_files() -> list[dict[str, object]]:
    files: list[dict[str, object]] = []
    # Bundle-local content (exclude scripts that rewrite digests circularly: include them).
    include_globs = [
        "README.md",
        "CITATION.cff",
        "limitations.md",
        "source-commit.txt",
        "release-manifest.json",
        "hardware-and-platform.json",
        "environment/**/*",
        "locks/**/*",
        "inputs/**/*",
        "configs/**/*",
        "scripts/**/*",
        "results/**/*",
        "verify.sh",
        "reproduce.sh",
    ]
    seen: set[str] = set()
    for pattern in include_globs:
        for path in sorted(BUNDLE.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(BUNDLE).as_posix()
            if rel in {"MANIFEST.json", "expected-digests.json"}:
                continue
            if rel in seen:
                continue
            seen.add(rel)
            files.append(
                {
                    "path": rel,
                    "sha256": _sha256(path),
                    "size": path.stat().st_size,
                }
            )

    # Snapshot pack.yaml + pack_tree digests as inputs.
    for pack_dir in sorted(PACKS.iterdir() if PACKS.is_dir() else []):
        if not pack_dir.is_dir():
            continue
        pack_yaml = pack_dir / "pack.yaml"
        if not pack_yaml.is_file():
            continue
        rel_pack = f"inputs/packs/{pack_dir.name}/pack.yaml"
        dest = BUNDLE / rel_pack
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Binary copy preserves LF from packs/** (see .gitattributes).
        dest.write_bytes(pack_yaml.read_bytes())
        files.append(
            {
                "path": rel_pack,
                "sha256": _sha256(dest),
                "size": dest.stat().st_size,
            }
        )
    files.sort(key=lambda e: str(e["path"]))
    return files


def _bundle_digest(files: list[dict[str, object]]) -> str:
    payload = [{"path": e["path"], "sha256": e["sha256"]} for e in files]
    payload_sorted = sorted(payload, key=lambda x: str(x["path"]))
    encoded = json.dumps(payload_sorted, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def refresh() -> None:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    for dirname in (
        "environment",
        "locks",
        "inputs",
        "configs",
        "scripts",
        "results",
    ):
        (BUNDLE / dirname).mkdir(parents=True, exist_ok=True)

    commit = _git_commit()
    (BUNDLE / "source-commit.txt").write_text(commit + "\n", encoding="utf-8")

    release_manifest = {
        "schema_version": "1",
        "project": "envassure",
        "status": "bundle-scaffold",
        "note": (
            "Full release-manifest.json is produced by Milestone A generators; "
            "this scaffold records pack + repo coordinates for local verify."
        ),
        "source_commit": commit,
        "packs": sorted(p.name for p in PACKS.iterdir() if p.is_dir()) if PACKS.is_dir() else [],
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (BUNDLE / "release-manifest.json").write_text(
        json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
    )

    hw = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "system": platform.system(),
        "processor": platform.processor(),
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    (BUNDLE / "hardware-and-platform.json").write_text(
        json.dumps(hw, indent=2) + "\n", encoding="utf-8"
    )

    (BUNDLE / "environment" / "python.txt").write_text(
        f"{sys.version}\n{platform.platform()}\n", encoding="utf-8"
    )
    (BUNDLE / "locks" / "README.md").write_text(
        "# Locks\n\nRelease CI attaches pip/uv lock digests here when publishing.\n",
        encoding="utf-8",
    )
    (BUNDLE / "configs" / "pack-verify.json").write_text(
        json.dumps({"command": "eac pack verify packs", "seed": 0}, indent=2) + "\n",
        encoding="utf-8",
    )
    (BUNDLE / "scripts" / "pack-verify.txt").write_text(
        "eac pack verify packs --json\n", encoding="utf-8"
    )
    # Non-empty + binary write: upload-artifact omits 0-byte files from directory
    # uploads; avoid text-mode CRLF so digests match across platforms.
    (BUNDLE / "results" / ".gitkeep").write_bytes(b"\n")

    files = _collect_files()
    digest = _bundle_digest(files)
    manifest = {
        "schema_version": "1",
        "bundle_id": "envassure-repro-bundle",
        "source_commit": commit,
        "generated_at": datetime.now(UTC).isoformat(),
        "files": files,
        "bundle_digest": digest,
    }
    (BUNDLE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    expected = {
        "bundle_digest": digest,
        "files": {str(e["path"]): str(e["sha256"]) for e in files},
    }
    (BUNDLE / "expected-digests.json").write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8"
    )
    print(f"refreshed {BUNDLE} digest={digest} files={len(files)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Rewrite digests and MANIFEST.")
    args = parser.parse_args()
    if args.refresh:
        refresh()
    else:
        refresh()


if __name__ == "__main__":
    main()
