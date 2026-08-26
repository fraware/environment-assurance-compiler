#!/usr/bin/env python3
"""Fail closed when GitHub Actions workflows use mutable remote references."""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

USES_RE = re.compile(r"^\s*(?:-\s*)?uses:\s*['\"]?([^'\"\s#]+)")
COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
CONTAINER_DIGEST_RE = re.compile(r"^docker://.+@sha256:[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    target: str
    reason: str


def _workflow_files(workflow_dir: Path) -> Iterable[Path]:
    yield from sorted(
        path
        for path in workflow_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".yml", ".yaml"}
    )


def check_workflow_dir(workflow_dir: Path) -> list[Finding]:
    """Return mutable or malformed remote ``uses:`` references."""
    findings: list[Finding] = []
    for path in _workflow_files(workflow_dir):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES_RE.match(line)
            if not match:
                continue
            target = match.group(1)

            # Repository-local actions and reusable workflows are content-addressed
            # by the checked-out repository revision and do not use an external ref.
            if target.startswith("./"):
                continue

            if target.startswith("docker://"):
                if not CONTAINER_DIGEST_RE.fullmatch(target):
                    findings.append(
                        Finding(
                            path,
                            line_no,
                            target,
                            "container action must use @sha256:<64-hex> digest",
                        )
                    )
                continue

            if "@" not in target:
                findings.append(
                    Finding(path, line_no, target, "remote action is missing @<commit-sha>")
                )
                continue

            _action, ref = target.rsplit("@", 1)
            if not COMMIT_SHA_RE.fullmatch(ref):
                findings.append(
                    Finding(
                        path,
                        line_no,
                        target,
                        "remote action must use an exact 40-character commit SHA",
                    )
                )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Require immutable references for all remote workflow actions."
    )
    parser.add_argument(
        "--workflow-dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Directory containing GitHub Actions workflow YAML files.",
    )
    args = parser.parse_args()

    workflow_dir = args.workflow_dir
    if not workflow_dir.is_dir():
        parser.error(f"workflow directory does not exist: {workflow_dir}")

    findings = check_workflow_dir(workflow_dir)
    if findings:
        for finding in findings:
            print(
                f"{finding.path}:{finding.line}: {finding.target}: {finding.reason}",
            )
        print(f"immutable action pin check failed: {len(findings)} finding(s)")
        return 1

    print("immutable action pin check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
