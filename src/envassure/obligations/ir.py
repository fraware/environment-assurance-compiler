"""Backend-neutral proof-obligation IR (EAC-R14).

Obligations declare *what must be evidenced*, not that a formal prover has
discharged the claim. Mechanism strength is explicit so packs cannot overstate
assurance.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash

ClaimKind = Literal[
    "authorization_preservation",
    "resource_conservation",
    "deterministic_reset_replay",
    "observation_separation",
    "reward_trace_binding",
    "idempotency_safety",
]

ObligationStatus = Literal[
    "generated",
    "open",
    "unsupported",
    "discharged",
    "deferred",
]

MechanismStrength = Literal[
    "syntactic",
    "runtime_checkable",
    "differential_evidence",
    "formal_unproven",
]


class ProofObligation(BaseModel):
    """One backend-neutral proof / evidence obligation compiled from IR."""

    model_config = ConfigDict(extra="forbid")

    id: str
    claim: str
    claim_kind: ClaimKind
    source_elements: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    backend_requirements: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    unsupported_conditions: list[str] = Field(default_factory=list)
    status: ObligationStatus = "generated"
    mechanism_strength: MechanismStrength = "runtime_checkable"
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class ProofObligationBundle(BaseModel):
    """Compiled set of proof obligations for a world / pack."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    environment_id: str
    ir_digest: str | None = None
    obligations: list[ProofObligation] = Field(default_factory=list)
    disclaimer: str = (
        "Proof obligations declare expected evidence classes and checkable "
        "runtime/differential properties. Presence of an obligation does not "
        "constitute a completed formal proof or production-fidelity claim."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        payload = self.model_dump(mode="json")
        return canonical_hash(payload)

    def by_kind(self, kind: ClaimKind) -> list[ProofObligation]:
        return [o for o in self.obligations if o.claim_kind == kind]
