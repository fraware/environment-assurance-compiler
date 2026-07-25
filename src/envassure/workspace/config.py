"""eac.toml workspace configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

import tomli_w
from pydantic import BaseModel, ConfigDict, Field


class ProjectSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = "0.1.0"
    description: str = ""
    ir_version: str = "0.2.0"


class CompilerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    require: str = ">=0.1.0a0"


class BuildSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["development", "release"] = "development"


class SourcePrecedenceSection(BaseModel):
    """Ordered authority preference used by reconciliation (later phases)."""

    model_config = ConfigDict(extra="forbid")

    order: list[str] = Field(
        default_factory=lambda: [
            "expert_decision",
            "executable_reference",
            "formal_policy",
            "database_schema",
            "api_contract",
            "approved_procedure",
            "operational_trace",
            "informal_documentation",
            "model_proposal",
            "unknown",
        ]
    )


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectSection
    compiler: CompilerSection = Field(default_factory=CompilerSection)
    build: BuildSection = Field(default_factory=BuildSection)
    source_precedence: SourcePrecedenceSection = Field(default_factory=SourcePrecedenceSection)


def load_workspace_config(path: Path) -> WorkspaceConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return WorkspaceConfig.model_validate(data)


def dump_workspace_config(config: WorkspaceConfig) -> str:
    payload: dict[str, Any] = config.model_dump(mode="python")
    return tomli_w.dumps(payload)


def write_workspace_config(path: Path, config: WorkspaceConfig) -> None:
    path.write_text(dump_workspace_config(config), encoding="utf-8")
