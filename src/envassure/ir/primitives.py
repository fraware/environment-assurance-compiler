"""Shared IR primitives."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Write-current IR schema version. Read window is current + prior stable minor.
IR_VERSION = "0.2.0"
IR_PRIOR_STABLE = "0.1.0"
SUPPORTED_READ_VERSIONS: frozenset[str] = frozenset({IR_PRIOR_STABLE, IR_VERSION})

JsonValue = Any


class ProvenanceRef(BaseModel):
    """Link from an IR element to sources and/or decisions."""

    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    notes: str | None = None


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
