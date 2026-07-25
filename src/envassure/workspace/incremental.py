"""Incremental rebuild / digest caching based on workspace build-state."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash, sha256_hex
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.workspace.layout import WorkspacePaths
from envassure.workspace.lock import BuildState, load_build_state


class SourceDigestMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    digests: dict[str, str] = Field(default_factory=dict)
    aggregate: str = ""

    def recompute_aggregate(self) -> str:
        self.aggregate = canonical_hash(self.digests)
        return self.aggregate


@dataclass(slots=True)
class IncrementalDecision:
    """Whether a rebuild can be skipped given current digests."""

    skip: bool
    reason: str
    source_digests: dict[str, str] = field(default_factory=dict)
    previous_digests: dict[str, str] = field(default_factory=dict)
    aggregate: str = ""
    report: DiagnosticReport = field(default_factory=DiagnosticReport)


def file_digest(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def digest_paths(paths: list[Path], *, root: Path | None = None) -> SourceDigestMap:
    """Digest a list of files; keys are relative posix paths when root is set."""
    digests: dict[str, str] = {}
    for path in sorted(paths, key=lambda p: str(p)):
        if not path.is_file():
            continue
        if root is not None:
            try:
                key = path.resolve().relative_to(root.resolve()).as_posix()
            except ValueError:
                key = path.as_posix()
        else:
            key = path.as_posix()
        digests[key] = file_digest(path)
    mapping = SourceDigestMap(digests=digests)
    mapping.recompute_aggregate()
    return mapping


def digest_workspace_sources(workspace: Path | WorkspacePaths) -> SourceDigestMap:
    """Digest ``sources/`` tree plus ``sources.yml`` and ``eac.toml``."""
    paths = workspace if isinstance(workspace, WorkspacePaths) else WorkspacePaths(root=workspace)
    files: list[Path] = []
    if paths.eac_toml.is_file():
        files.append(paths.eac_toml)
    if paths.sources_yml.is_file():
        files.append(paths.sources_yml)
    if paths.sources_dir.is_dir():
        for path in sorted(paths.sources_dir.rglob("*")):
            if path.is_file() and path.name != ".gitkeep":
                files.append(path)
    return digest_paths(files, root=paths.root)


def decide_incremental_rebuild(
    workspace: Path | WorkspacePaths,
    *,
    force: bool = False,
    build_state: BuildState | None = None,
) -> IncrementalDecision:
    """Return skip=True when source digests match last successful build-state."""
    paths = workspace if isinstance(workspace, WorkspacePaths) else WorkspacePaths(root=workspace)
    report = DiagnosticReport()
    current = digest_workspace_sources(paths)
    previous: dict[str, str] = {}
    state = build_state
    if state is None and paths.build_state_json.is_file():
        state = load_build_state(paths.build_state_json)
    if state is not None and state.source_digests:
        previous = dict(state.source_digests)

    if force:
        return IncrementalDecision(
            skip=False,
            reason="forced rebuild",
            source_digests=current.digests,
            previous_digests=previous,
            aggregate=current.aggregate,
            report=report,
        )

    if not previous:
        return IncrementalDecision(
            skip=False,
            reason="no prior source digests in build-state",
            source_digests=current.digests,
            previous_digests={},
            aggregate=current.aggregate,
            report=report,
        )

    if previous == current.digests:
        report.add(
            make_diagnostic(
                "EAC8007",
                reason=f"aggregate={current.aggregate[:16]}",
                subject=str(paths.root),
            )
        )
        return IncrementalDecision(
            skip=True,
            reason="source digests unchanged",
            source_digests=current.digests,
            previous_digests=previous,
            aggregate=current.aggregate,
            report=report,
        )

    changed = sorted(set(previous) | set(current.digests))
    delta = [k for k in changed if previous.get(k) != current.digests.get(k)]
    return IncrementalDecision(
        skip=False,
        reason=f"source digest drift ({len(delta)} path(s))",
        source_digests=current.digests,
        previous_digests=previous,
        aggregate=current.aggregate,
        report=report,
    )


def decide_incremental_lint(
    ir_path: Path,
    *,
    workspace: Path | WorkspacePaths | None = None,
    force: bool = False,
    build_state: BuildState | None = None,
) -> IncrementalDecision:
    """Return skip=True when IR digest matches last successful lint in build-state."""
    report = DiagnosticReport()
    paths: WorkspacePaths | None
    if workspace is not None:
        paths = (
            workspace if isinstance(workspace, WorkspacePaths) else WorkspacePaths(root=workspace)
        )
    else:
        paths = _find_workspace(ir_path)

    digest = file_digest(ir_path) if ir_path.is_file() else ""
    previous: dict[str, str] = {}
    state = build_state
    if state is None and paths is not None and paths.build_state_json.is_file():
        state = load_build_state(paths.build_state_json)
    if state is not None:
        previous = {
            "lint_ir": state.artifact_digests.get("lint_ir", ""),
            "lint_status": state.artifact_digests.get("lint_status", ""),
        }

    if force:
        return IncrementalDecision(
            skip=False,
            reason="forced lint",
            source_digests={"ir": digest},
            previous_digests=previous,
            aggregate=digest,
            report=report,
        )

    if not ir_path.is_file():
        return IncrementalDecision(
            skip=False,
            reason="IR path missing",
            source_digests={"ir": digest},
            previous_digests=previous,
            aggregate=digest,
            report=report,
        )

    if previous.get("lint_ir") == digest and previous.get("lint_status") == "ok":
        report.add(
            make_diagnostic(
                "EAC8008",
                reason=f"digest={digest[:16]}",
                subject=str(ir_path),
            )
        )
        return IncrementalDecision(
            skip=True,
            reason="IR digest unchanged since last successful lint",
            source_digests={"ir": digest},
            previous_digests=previous,
            aggregate=digest,
            report=report,
        )

    return IncrementalDecision(
        skip=False,
        reason="IR digest drifted or no prior lint",
        source_digests={"ir": digest},
        previous_digests=previous,
        aggregate=digest,
        report=report,
    )


def record_lint_state(
    ir_path: Path,
    *,
    workspace: Path | WorkspacePaths | None = None,
    status: str = "ok",
) -> BuildState | None:
    """Record successful lint digest into workspace build-state when available."""
    paths: WorkspacePaths | None
    if workspace is not None:
        paths = (
            workspace if isinstance(workspace, WorkspacePaths) else WorkspacePaths(root=workspace)
        )
    else:
        paths = _find_workspace(ir_path)
    if paths is None:
        return None
    digest = file_digest(ir_path)
    existing = (
        load_build_state(paths.build_state_json) if paths.build_state_json.is_file() else None
    )
    source_digests = (
        dict(existing.source_digests) if existing else digest_workspace_sources(paths).digests
    )
    artifact_digests = dict(existing.artifact_digests) if existing else {}
    artifact_digests["lint_ir"] = digest
    artifact_digests["lint_status"] = status
    return record_build_state(
        paths,
        command="lint",
        status=status,
        source_digests=source_digests,
        artifact_digests=artifact_digests,
    )


def _find_workspace(start: Path) -> WorkspacePaths | None:
    """Walk parents looking for ``eac.toml``."""
    cur = start.resolve()
    if cur.is_file():
        cur = cur.parent
    for candidate in [cur, *cur.parents]:
        if (candidate / "eac.toml").is_file():
            return WorkspacePaths(root=candidate)
    return None


def record_build_state(
    workspace: Path | WorkspacePaths,
    *,
    command: str,
    status: str,
    source_digests: dict[str, str] | None = None,
    artifact_digests: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> BuildState:
    """Persist build-state with source digests for incremental skips."""
    paths = workspace if isinstance(workspace, WorkspacePaths) else WorkspacePaths(root=workspace)
    digests = source_digests
    if digests is None:
        digests = digest_workspace_sources(paths).digests

    artifacts = dict(artifact_digests or {})
    # Keep a nested copy for older readers that only look at artifact_digests.
    artifacts["sources_aggregate"] = canonical_hash(digests)

    state = BuildState(
        last_command=command,
        last_status=status,
        artifact_digests=artifacts,
        source_digests=digests,
        last_sources_aggregate=canonical_hash(digests),
    )
    if extra:
        # Store opaque extras under artifact_digests keys with prefix.
        for key, value in extra.items():
            if isinstance(value, str):
                state.artifact_digests[f"extra:{key}"] = value
            else:
                state.artifact_digests[f"extra:{key}"] = canonical_hash(value)

    paths.eac_dir.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json")
    paths.build_state_json.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return state
