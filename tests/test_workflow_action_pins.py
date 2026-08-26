"""Regression tests for the GitHub Actions immutable-reference policy."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "check_workflow_action_pins.py"

spec = importlib.util.spec_from_file_location("check_workflow_action_pins", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
check_workflow_dir = module.check_workflow_dir


def _write(workflow_dir: Path, text: str) -> None:
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "test.yml").write_text(text, encoding="utf-8")


def test_accepts_exact_remote_commit_sha(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    _write(
        workflows,
        "steps:\n  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4\n",
    )
    assert check_workflow_dir(workflows) == []


def test_rejects_mutable_remote_tag(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    _write(workflows, "steps:\n  - uses: actions/checkout@v4\n")
    findings = check_workflow_dir(workflows)
    assert len(findings) == 1
    assert "40-character commit SHA" in findings[0].reason


def test_accepts_repository_local_action(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    _write(workflows, "steps:\n  - uses: ./.github/actions/local-check\n")
    assert check_workflow_dir(workflows) == []


def test_container_action_requires_sha256_digest(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    _write(workflows, "steps:\n  - uses: docker://alpine:3.20\n")
    findings = check_workflow_dir(workflows)
    assert len(findings) == 1
    assert "@sha256" in findings[0].reason


def test_accepts_digest_pinned_container_action(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    digest = "a" * 64
    _write(workflows, f"steps:\n  - uses: docker://alpine@sha256:{digest}\n")
    assert check_workflow_dir(workflows) == []


def test_rejects_remote_action_without_ref(tmp_path: Path) -> None:
    workflows = tmp_path / "workflows"
    _write(workflows, "steps:\n  - uses: owner/action\n")
    findings = check_workflow_dir(workflows)
    assert len(findings) == 1
    assert "missing @<commit-sha>" in findings[0].reason
