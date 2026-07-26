"""Scoped fidelity claim ledger (ADR-0005): no composite score."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from envassure.canonical import canonical_hash

FidelityClaimStatus = Literal[
    "unassessed",
    "structurally_valid",
    "trace_supported",
    "expert_reviewed",
    "empirically_compared",
]

FIDELITY_CLAIM_STATUSES: frozenset[str] = frozenset(
    {
        "unassessed",
        "structurally_valid",
        "trace_supported",
        "expert_reviewed",
        "empirically_compared",
    }
)

# Statuses below expert_reviewed must keep known_gaps visible.
_GAPS_REQUIRED_BELOW: frozenset[str] = frozenset(
    {
        "unassessed",
        "structurally_valid",
        "trace_supported",
    }
)


class ClaimScope(BaseModel):
    """Required scope for a fidelity claim (environment + IR elements and/or dimension)."""

    model_config = ConfigDict(extra="forbid")

    environment_id: str
    element_ids: list[str] = Field(default_factory=list)
    dimension: str | None = None

    @model_validator(mode="after")
    def _require_element_or_dimension(self) -> ClaimScope:
        if not self.environment_id.strip():
            raise ValueError("scope.environment_id is required")
        if not self.element_ids and not (self.dimension and self.dimension.strip()):
            raise ValueError("scope requires element_ids and/or dimension")
        return self


class FidelityClaim(BaseModel):
    """One scoped fidelity claim with evidence and explicit gaps."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    scope: ClaimScope
    evidence: list[str] = Field(default_factory=list)
    coverage: str = ""
    reviewer: str | None = None
    known_gaps: list[str] = Field(default_factory=list)
    status: FidelityClaimStatus = "unassessed"

    @field_validator("claim")
    @classmethod
    def _nonempty_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim statement must be non-empty")
        return value

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        if value not in FIDELITY_CLAIM_STATUSES:
            raise ValueError(f"unknown fidelity claim status: {value!r}")
        return value

    @model_validator(mode="after")
    def _gaps_visible_below_expert(self) -> FidelityClaim:
        if self.status in _GAPS_REQUIRED_BELOW and not self.known_gaps:
            raise ValueError(
                f"known_gaps must remain visible when status is {self.status!r} "
                "(below expert_reviewed)"
            )
        return self


class FidelityLedger(BaseModel):
    """Ledger of scoped fidelity claims — never a single aggregate score."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    environment_id: str
    claims: list[FidelityClaim] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _reject_score_fields(self) -> FidelityLedger:
        forbidden = {
            "score",
            "aggregate_score",
            "composite_score",
            "fidelity_score",
            "average",
            "mean",
        }
        overlap = forbidden & set(self.metadata)
        if overlap:
            raise ValueError(
                f"fidelity ledger forbids aggregate score metadata keys: {sorted(overlap)}"
            )
        for claim in self.claims:
            if claim.scope.environment_id != self.environment_id:
                raise ValueError(
                    f"claim scope.environment_id {claim.scope.environment_id!r} "
                    f"does not match ledger environment_id {self.environment_id!r}"
                )
        return self

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    def claims_by_status(self) -> dict[str, list[FidelityClaim]]:
        grouped: dict[str, list[FidelityClaim]] = {s: [] for s in sorted(FIDELITY_CLAIM_STATUSES)}
        for claim in self.claims:
            grouped[claim.status].append(claim)
        return grouped

    def to_pack_member(self) -> bytes:
        return (json.dumps(self.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")


def average_fidelity_score(*_args: Any, **_kwargs: Any) -> float:
    """Rejected API: EnvAssure never averages fidelity dimensions into a score."""
    raise ValueError(
        "aggregate fidelity scores are forbidden (ADR-0005); "
        "report scoped FidelityClaim entries instead"
    )


def mean_fidelity(*_args: Any, **_kwargs: Any) -> float:
    """Rejected alias for average_fidelity_score."""
    return average_fidelity_score(*_args, **_kwargs)


def composite_fidelity_score(*_args: Any, **_kwargs: Any) -> float:
    """Rejected alias for average_fidelity_score."""
    return average_fidelity_score(*_args, **_kwargs)


def load_fidelity_ledger(path: Path) -> FidelityLedger:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return FidelityLedger.model_validate(data)


def save_fidelity_ledger(path: Path, ledger: FidelityLedger) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )


def ledger_from_world(
    world: Any,
    *,
    status: FidelityClaimStatus = "structurally_valid",
    known_gaps: list[str] | None = None,
) -> FidelityLedger:
    """Seed a minimal ledger from declared IR fidelity (not empirical evidence)."""
    gaps = list(known_gaps) if known_gaps is not None else list(world.known_unsupported_behavior)
    if status in _GAPS_REQUIRED_BELOW and not gaps:
        gaps = [
            "No empirical comparison recorded; declared level is not production parity evidence."
        ]
    claim = FidelityClaim(
        claim=(
            f"Declared fidelity level {world.declared_fidelity_level} "
            f"for environment {world.environment_id}."
        ),
        scope=ClaimScope(
            environment_id=world.environment_id,
            element_ids=[world.environment_id],
            dimension="declared_level",
        ),
        evidence=[f"ir:declared_fidelity_level:{world.declared_fidelity_level}"],
        coverage="declared_only",
        reviewer=None,
        known_gaps=gaps,
        status=status,
    )
    return FidelityLedger(environment_id=world.environment_id, claims=[claim])
