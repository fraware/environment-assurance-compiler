"""Obligation evidence records for assurance-case integration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash
from envassure.obligations.ir import ProofObligationBundle

EvidenceKind = Literal[
    "opa_eval",
    "opa_test",
    "runtime_check",
    "differential",
    "manual",
]

EvidenceStatus = Literal["pass", "fail", "indeterminate", "skipped"]


class ObligationEvidence(BaseModel):
    """One piece of evidence discharging (or failing) an obligation."""

    model_config = ConfigDict(extra="forbid")

    obligation_id: str
    kind: EvidenceKind
    status: EvidenceStatus
    detail: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class ObligationEvidenceReport(BaseModel):
    """Collected evidence for a compiled obligation bundle."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    environment_id: str
    bundle_digest: str | None = None
    evidence: list[ObligationEvidence] = Field(default_factory=list)
    disclaimer: str = (
        "Evidence records document checks performed against declared obligations. "
        "They do not constitute a completed formal proof or production-fidelity claim."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    def to_assurance_case_fragment(self) -> dict[str, Any]:
        """Shape suitable for embedding into an assurance-case / pack report."""
        return {
            "kind": "obligation_evidence",
            "environment_id": self.environment_id,
            "bundle_digest": self.bundle_digest,
            "evidence": [e.model_dump(mode="json") for e in self.evidence],
            "digest": self.content_digest(),
            "disclaimer": self.disclaimer,
        }


def build_evidence_report(
    bundle: ProofObligationBundle,
    evidence: list[ObligationEvidence],
    *,
    metadata: dict[str, Any] | None = None,
) -> ObligationEvidenceReport:
    return ObligationEvidenceReport(
        environment_id=bundle.environment_id,
        bundle_digest=bundle.content_digest(),
        evidence=list(evidence),
        metadata=metadata or {},
    )
