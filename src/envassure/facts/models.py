"""SemanticFact and ConfidenceRecord models (no bare float confidence)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.ir.primitives import EntityRef

EvidenceClass = Literal[
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

# How a fact was obtained from its source (orthogonal to EvidenceClass authority).
DerivationClass = Literal["direct", "observed", "inferred", "expert"]

ExtractorCertainty = Literal["high", "medium", "low", "unknown"]
ConflictStatus = Literal["none", "conflict", "alias", "unresolved"]
ReviewerStatus = Literal["unreviewed", "accepted", "rejected", "deferred"]
FactStatus = Literal["candidate", "accepted", "rejected", "superseded"]


class ConfidenceRecord(BaseModel):
    """Structured confidence — never a bare float."""

    model_config = ConfigDict(extra="forbid")

    evidence_class: EvidenceClass = "unknown"
    derivation_class: DerivationClass = "direct"
    extractor_certainty: ExtractorCertainty = "unknown"
    conflict_status: ConflictStatus = "none"
    reviewer_status: ReviewerStatus = "unreviewed"
    notes: str | None = None


class TemporalScope(BaseModel):
    """Optional applicability window for a fact."""

    model_config = ConfigDict(extra="forbid")

    start: str | None = None
    end: str | None = None
    label: str | None = None


class SemanticFact(BaseModel):
    """Candidate or accepted semantic claim extracted from a source."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str
    subject: EntityRef
    predicate: str
    value: Any
    source_refs: list[str] = Field(default_factory=list)
    extraction_method: str
    confidence: ConfidenceRecord = Field(default_factory=ConfidenceRecord)
    temporal_scope: TemporalScope | None = None
    status: FactStatus = "candidate"
    kind_tags: list[str] = Field(default_factory=list)


def make_fact_id(
    *,
    subject_kind: str,
    subject_id: str,
    predicate: str,
    source: str,
    suffix: str = "",
) -> str:
    """Deterministic fact id for stable round-trips."""
    base = f"fact:{subject_kind}:{subject_id}:{predicate}:{source}"
    if suffix:
        return f"{base}:{suffix}"
    return base
