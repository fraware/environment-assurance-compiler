"""SourceArtifact model and sources.yml manifest."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AuthorityClass = Literal[
    "executable_reference",
    "formal_policy",
    "database_schema",
    "api_contract",
    "operational_trace",
    "approved_procedure",
    "expert_decision",
    "informal_documentation",
    "model_proposal",
    "unknown",
]

AUTHORITY_CLASSES: frozenset[str] = frozenset(
    {
        "executable_reference",
        "formal_policy",
        "database_schema",
        "api_contract",
        "operational_trace",
        "approved_procedure",
        "expert_decision",
        "informal_documentation",
        "model_proposal",
        "unknown",
    }
)


class ConfidentialityClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class CompletenessDeclaration(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class TimeInterval(BaseModel):
    """Applicable time interval for a source artifact."""

    model_config = ConfigDict(extra="forbid")

    start: datetime | None = None
    end: datetime | None = None


class SourceArtifact(BaseModel):
    """Provenanced source input (§9.1)."""

    model_config = ConfigDict(extra="forbid")

    source_id: Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z0-9._:-]+$")]
    kind: Annotated[str, Field(min_length=1)]
    uri: str | None = None
    path: str | None = None
    digest: Annotated[str, Field(min_length=1)]
    acquired_at: datetime
    authority: AuthorityClass
    confidentiality: ConfidentialityClass = ConfidentialityClass.INTERNAL
    version: str | None = None
    commit: str | None = None
    parser: str | None = None
    parser_version: str | None = None
    applicable_interval: TimeInterval | None = None
    completeness: CompletenessDeclaration = CompletenessDeclaration.UNKNOWN
    trust_notes: str | None = None

    @field_validator("authority")
    @classmethod
    def _check_authority(cls, value: str) -> str:
        if value not in AUTHORITY_CLASSES:
            raise ValueError(f"unknown authority class: {value}")
        return value

    @model_validator(mode="after")
    def _require_locator(self) -> Self:
        if self.uri is None and self.path is None:
            raise ValueError("SourceArtifact requires uri or path")
        return self


class SourcesManifest(BaseModel):
    """Top-level sources.yml document."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    sources: list[SourceArtifact] = Field(default_factory=list)

    def by_id(self) -> dict[str, SourceArtifact]:
        return {s.source_id: s for s in self.sources}

    def digests(self) -> dict[str, str]:
        return {s.source_id: s.digest for s in self.sources}


def load_sources_manifest(path: Path) -> SourcesManifest:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("sources.yml must be a mapping")
    return SourcesManifest.model_validate(data)


def save_sources_manifest(path: Path, manifest: SourcesManifest) -> None:
    payload = manifest.model_dump(mode="json")
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
