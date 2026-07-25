"""Canonical workspace paths and layout constants."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WORKSPACE_DIRS: tuple[str, ...] = (
    "sources",
    "cache",
    "facts",
    "decisions",
    "ir",
    "generated",
    "validation",
    "reports",
    ".eac",
)

WORKSPACE_FILES: tuple[str, ...] = (
    "eac.toml",
    "sources.yml",
)


@dataclass(frozen=True, slots=True)
class WorkspacePaths:
    """Resolved paths for an EnvAssure authoring workspace."""

    root: Path

    @property
    def eac_toml(self) -> Path:
        return self.root / "eac.toml"

    @property
    def sources_yml(self) -> Path:
        return self.root / "sources.yml"

    @property
    def sources_dir(self) -> Path:
        return self.root / "sources"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def facts_dir(self) -> Path:
        return self.root / "facts"

    @property
    def decisions_dir(self) -> Path:
        return self.root / "decisions"

    @property
    def ir_dir(self) -> Path:
        return self.root / "ir"

    @property
    def generated_dir(self) -> Path:
        return self.root / "generated"

    @property
    def validation_dir(self) -> Path:
        return self.root / "validation"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    @property
    def eac_dir(self) -> Path:
        return self.root / ".eac"

    @property
    def lock_json(self) -> Path:
        return self.eac_dir / "lock.json"

    @property
    def plugin_lock_json(self) -> Path:
        return self.eac_dir / "plugin-lock.json"

    @property
    def build_state_json(self) -> Path:
        return self.eac_dir / "build-state.json"

    def is_workspace(self) -> bool:
        return self.eac_toml.is_file()

    def missing_required(self) -> list[str]:
        missing: list[str] = []
        if not self.eac_toml.is_file():
            missing.append("eac.toml")
        if not self.sources_yml.is_file():
            missing.append("sources.yml")
        if not self.eac_dir.is_dir():
            missing.append(".eac/")
        return missing
