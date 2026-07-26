"""Diagnostic data models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """Diagnostic severity levels."""

    ERROR = "error"
    WARNING = "warning"
    NOTE = "note"
    HELP = "help"


class SourceRef(BaseModel):
    """Reference to a location in a source artifact."""

    model_config = ConfigDict(extra="forbid")

    path: str
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None
    excerpt: str | None = None


class Diagnostic(BaseModel):
    """A single compiler diagnostic with stable code and machine details."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^EAC[1-9]\d{3}$")
    severity: Severity
    summary: str
    subject: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    affected_artifacts: list[str] = Field(default_factory=list)
    consequence: str | None = None
    suggested_repair: str | None = None
    claim_impact: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    def is_blocking(self) -> bool:
        """Return True if this diagnostic should fail the process."""
        return self.severity is Severity.ERROR


class DiagnosticReport(BaseModel):
    """Collection of diagnostics plus optional context."""

    model_config = ConfigDict(extra="forbid")

    diagnostics: list[Diagnostic] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)

    def add(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def extend(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)

    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity is Severity.ERROR]

    def has_errors(self) -> bool:
        return any(d.is_blocking() for d in self.diagnostics)

    def highest_severity(self) -> Severity | None:
        if not self.diagnostics:
            return None
        order = {
            Severity.HELP: 0,
            Severity.NOTE: 1,
            Severity.WARNING: 2,
            Severity.ERROR: 3,
        }
        return max(self.diagnostics, key=lambda d: order[d.severity]).severity
