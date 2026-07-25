"""Lock files and build state under `.eac/`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure import __version__
from envassure.canonical import canonical_dumps, canonical_hash


class PluginPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    digest: str | None = None


class DecisionPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    digest: str


class ModelProposalMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    digest: str
    accepted: bool = False


class ConnectorPin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str


class LockFile(BaseModel):
    """Pins compiler, plugins, templates, sources, decisions, and deps."""

    model_config = ConfigDict(extra="forbid")

    lock_version: Literal[1] = 1
    compiler_version: str
    plugins: list[PluginPin] = Field(default_factory=list)
    template_digests: dict[str, str] = Field(default_factory=dict)
    source_digests: dict[str, str] = Field(default_factory=dict)
    accepted_decisions: list[DecisionPin] = Field(default_factory=list)
    model_proposals: list[ModelProposalMeta] = Field(default_factory=list)
    reference_connectors: list[ConnectorPin] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class PluginLockFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lock_version: Literal[1] = 1
    plugins: list[PluginPin] = Field(default_factory=list)


class BuildState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_version: Literal[1] = 1
    last_command: str | None = None
    last_status: str | None = None
    artifact_digests: dict[str, str] = Field(default_factory=dict)
    source_digests: dict[str, str] = Field(default_factory=dict)
    last_sources_aggregate: str | None = None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = canonical_dumps(payload)
    # Pretty-print for humans while keeping key order sorted for stability.
    parsed = json.loads(text)
    path.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_default_locks(
    eac_dir: Path,
    *,
    source_digests: dict[str, str] | None = None,
    compiler_version: str | None = None,
) -> LockFile:
    lock = LockFile(
        compiler_version=compiler_version or __version__,
        source_digests=source_digests or {},
        dependencies={"envassure": compiler_version or __version__},
    )
    _write_json(eac_dir / "lock.json", lock.model_dump(mode="json"))
    plugin_lock = PluginLockFile()
    _write_json(eac_dir / "plugin-lock.json", plugin_lock.model_dump(mode="json"))
    build_state = BuildState(last_command="init", last_status="ok")
    _write_json(eac_dir / "build-state.json", build_state.model_dump(mode="json"))
    return lock


def load_lock(path: Path) -> LockFile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return LockFile.model_validate(data)


def load_plugin_lock(path: Path) -> PluginLockFile:
    data = json.loads(path.read_text(encoding="utf-8"))
    return PluginLockFile.model_validate(data)


def load_build_state(path: Path) -> BuildState:
    data = json.loads(path.read_text(encoding="utf-8"))
    return BuildState.model_validate(data)


def check_lock_consistency(
    lock: LockFile,
    *,
    source_digests: dict[str, str],
    compiler_version: str,
) -> list[str]:
    """Return human-readable inconsistency reasons (empty if consistent)."""
    reasons: list[str] = []
    if lock.compiler_version != compiler_version:
        reasons.append(
            f"compiler_version lock={lock.compiler_version!r} runtime={compiler_version!r}"
        )
    locked = lock.source_digests
    for source_id, digest in source_digests.items():
        if source_id not in locked:
            reasons.append(f"source {source_id!r} missing from lock")
        elif locked[source_id] != digest:
            reasons.append(
                f"source {source_id!r} digest mismatch lock={locked[source_id]!r} actual={digest!r}"
            )
    for source_id in locked:
        if source_id not in source_digests:
            reasons.append(f"lock references missing source {source_id!r}")
    return reasons
