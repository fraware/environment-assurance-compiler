"""Shared IR primitives."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Write-current IR schema version. Read window is current + prior stable minor.
IR_VERSION = "0.2.0"
IR_PRIOR_STABLE = "0.1.0"
SUPPORTED_READ_VERSIONS: frozenset[str] = frozenset({IR_PRIOR_STABLE, IR_VERSION})

JsonValue = Any

# Compiled view of how an IR element was obtained (orthogonal to fact DerivationClass).
OriginKind = Literal[
    "source_derived",
    "inferred",
    "default",
    "unresolved_conflict",
    "human_decision",
    "simulator_only",
    "external_connector",
    "fidelity_evidence",
]

ORIGIN_KINDS: frozenset[str] = frozenset(
    {
        "source_derived",
        "inferred",
        "default",
        "unresolved_conflict",
        "human_decision",
        "simulator_only",
        "external_connector",
        "fidelity_evidence",
    }
)

# Fact-layer derivation → default IR origin_kind (ingestion truth → compiled view).
_DERIVATION_TO_ORIGIN: dict[str, OriginKind] = {
    "direct": "source_derived",
    "observed": "source_derived",
    "inferred": "inferred",
    "expert": "human_decision",
}


class ProvenanceRef(BaseModel):
    """Link from an IR element to sources and/or decisions."""

    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    origin_kind: OriginKind | None = None
    notes: str | None = None


def origin_kind_for_derivation(derivation_class: str) -> OriginKind:
    """Map fact-layer ``DerivationClass`` to an IR ``origin_kind``."""
    try:
        return _DERIVATION_TO_ORIGIN[derivation_class]
    except KeyError as exc:
        raise ValueError(f"unknown derivation_class: {derivation_class!r}") from exc


def origin_kind_conflict_reason(
    origin_kind: OriginKind | None,
    derivation_classes: Iterable[str],
) -> str | None:
    """Return a conflict reason if origin_kind is incompatible with fact derivations.

    Hard rule: ``inferred`` facts must never be tagged ``source_derived``.
    """
    if origin_kind is None:
        return None
    classes = {c for c in derivation_classes if c}
    if not classes:
        return None
    if origin_kind == "source_derived" and "inferred" in classes:
        return "inferred derivation_class cannot be tagged origin_kind=source_derived"
    if (
        origin_kind == "inferred"
        and "inferred" not in classes
        and classes
        <= {
            "direct",
            "observed",
        }
    ):
        return (
            f"origin_kind=inferred is incompatible with derivation_class values {sorted(classes)}"
        )
    return None


def validate_provenance_origin(
    provenance: ProvenanceRef,
    *,
    derivation_classes: Iterable[str] = (),
    subject: str | None = None,
) -> str | None:
    """Validate provenance origin_kind; return reason string or None when valid."""
    if provenance.origin_kind is not None and provenance.origin_kind not in ORIGIN_KINDS:
        return f"unknown origin_kind {provenance.origin_kind!r}"
    reason = origin_kind_conflict_reason(provenance.origin_kind, derivation_classes)
    if reason is None:
        return None
    if subject:
        return f"{subject}: {reason}"
    return reason


class EntityRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    id: str


class ConstraintExpr(BaseModel):
    """Lightweight constraint expression (opaque string + optional structured form)."""

    model_config = ConfigDict(extra="forbid")

    expression: str
    structured: dict[str, Any] | None = None


FailureCategory = Literal[
    "validation",
    "authorization",
    "business_rule",
    "dependency",
    "timeout",
    "partial_commit",
    "conflict",
    "rate_limit",
    "stale_state",
    "resource_exhaustion",
    "unknown_external",
]

StateTypeName = Literal[
    "scalar",
    "enum",
    "record",
    "list",
    "set",
    "map",
    "graph",
    "queue",
    "resource_counter",
    "timestamp",
    "duration",
    "opaque_external_ref",
]

DeterminismClass = Literal[
    "fully_deterministic",
    "seeded_recorded_externals",
    "statistical",
    "externally_nondeterministic",
]

VerifierStatus = Literal[
    "draft",
    "tested",
    "differentially_validated",
    "qualified_external",
    "deprecated",
    "candidate",
]

AmbiguityStatus = Literal[
    "open",
    "accepted",
    "deferred",
    "rejected",
]
