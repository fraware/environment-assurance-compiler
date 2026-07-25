"""Typed comparison dimensions and tolerances for differential validation."""

from __future__ import annotations

from enum import StrEnum
from math import sqrt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic
from envassure.differential.connector import ProbeOutcome
from envassure.ir.models import WorldDefinition


class ComparisonDimension(StrEnum):
    SUCCESS = "success"
    OBSERVATION = "observation"
    STATE = "state"
    FAILURE = "failure"
    AUTHORIZATION = "authorization"
    RETRY = "retry"
    IDEMPOTENCY = "idempotency"
    LATENCY = "latency"


class ComparisonTolerances(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: float = 50.0
    numeric_abs: float = 1e-6
    numeric_rel: float = 1e-3
    stochastic_min_samples: int = 30
    stochastic_z: float = 1.96  # ~95% Wald interval


class DimensionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ComparisonDimension
    matched: bool
    detail: str | None = None
    statistical: bool = False
    confidence_note: str | None = None


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    matched: bool
    verdicts: list[DimensionVerdict] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @property
    def failing_dimensions(self) -> list[ComparisonDimension]:
        return [v.dimension for v in self.verdicts if not v.matched]


def compare_outcomes(
    reference: ProbeOutcome,
    candidate: ProbeOutcome,
    *,
    world: WorldDefinition | None = None,
    tolerances: ComparisonTolerances | None = None,
    dimensions: list[ComparisonDimension] | None = None,
    stochastic_samples: list[tuple[bool, bool]] | None = None,
) -> ComparisonResult:
    """
    Compare reference vs candidate outcomes on typed dimensions.

    For stochastic worlds, pass *stochastic_samples* as pairs of
    ``(reference_success, candidate_success)``; binary equality is not used
    when sample size is below ``stochastic_min_samples``.
    """
    tol = tolerances or ComparisonTolerances()
    dims = dimensions or [
        ComparisonDimension.SUCCESS,
        ComparisonDimension.OBSERVATION,
        ComparisonDimension.STATE,
        ComparisonDimension.FAILURE,
        ComparisonDimension.AUTHORIZATION,
        ComparisonDimension.RETRY,
        ComparisonDimension.IDEMPOTENCY,
        ComparisonDimension.LATENCY,
    ]
    verdicts: list[DimensionVerdict] = []
    diagnostics: list[Diagnostic] = []
    probe_id = candidate.probe_id or reference.probe_id

    is_statistical = bool(
        world is not None and world.determinism in {"statistical", "externally_nondeterministic"}
    )

    for dim in dims:
        if dim is ComparisonDimension.SUCCESS and is_statistical and stochastic_samples is not None:
            verdict = _statistical_success(stochastic_samples, tol)
            verdicts.append(verdict)
            if verdict.confidence_note:
                diagnostics.append(
                    make_diagnostic(
                        "EAC7002",
                        reason=verdict.confidence_note,
                        subject=probe_id,
                    )
                )
            continue

        verdict = _compare_dimension(dim, reference, candidate, tol)
        verdicts.append(verdict)
        if not verdict.matched:
            diagnostics.append(
                make_diagnostic(
                    "EAC7001",
                    reason=(
                        f"dimension {dim.value} mismatch on probe {probe_id}: {verdict.detail}"
                    ),
                    subject=probe_id,
                    details={"dimension": dim.value, "detail": verdict.detail},
                )
            )

    matched = all(v.matched for v in verdicts)
    return ComparisonResult(
        probe_id=probe_id,
        matched=matched,
        verdicts=verdicts,
        diagnostics=diagnostics,
    )


def _compare_dimension(
    dim: ComparisonDimension,
    reference: ProbeOutcome,
    candidate: ProbeOutcome,
    tol: ComparisonTolerances,
) -> DimensionVerdict:
    if dim is ComparisonDimension.SUCCESS:
        ok = reference.success == candidate.success
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else f"ref={reference.success} cand={candidate.success}",
        )
    if dim is ComparisonDimension.OBSERVATION:
        ok = _mapping_close(reference.observation, candidate.observation, tol)
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else "observation maps differ beyond tolerance",
        )
    if dim is ComparisonDimension.STATE:
        ok = _mapping_close(reference.state, candidate.state, tol)
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else "state maps differ beyond tolerance",
        )
    if dim is ComparisonDimension.FAILURE:
        ok = reference.failure_id == candidate.failure_id
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else f"ref={reference.failure_id!r} cand={candidate.failure_id!r}",
        )
    if dim is ComparisonDimension.AUTHORIZATION:
        if reference.authorization_ok is None and candidate.authorization_ok is None:
            return DimensionVerdict(dimension=dim, matched=True, detail="unset")
        ok = reference.authorization_ok == candidate.authorization_ok
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None
            if ok
            else f"ref={reference.authorization_ok} cand={candidate.authorization_ok}",
        )
    if dim is ComparisonDimension.RETRY:
        ok = reference.retry_count == candidate.retry_count
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else f"ref={reference.retry_count} cand={candidate.retry_count}",
        )
    if dim is ComparisonDimension.IDEMPOTENCY:
        if reference.idempotent_replay_equal is None and candidate.idempotent_replay_equal is None:
            return DimensionVerdict(dimension=dim, matched=True, detail="unset")
        ok = reference.idempotent_replay_equal == candidate.idempotent_replay_equal
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else "idempotent replay disagreement",
        )
    if dim is ComparisonDimension.LATENCY:
        if reference.latency_ms is None or candidate.latency_ms is None:
            return DimensionVerdict(dimension=dim, matched=True, detail="unset")
        ok = abs(reference.latency_ms - candidate.latency_ms) <= tol.latency_ms
        return DimensionVerdict(
            dimension=dim,
            matched=ok,
            detail=None if ok else f"|Δ|={abs(reference.latency_ms - candidate.latency_ms):.3f}ms",
        )
    return DimensionVerdict(dimension=dim, matched=True)


def _statistical_success(
    samples: list[tuple[bool, bool]],
    tol: ComparisonTolerances,
) -> DimensionVerdict:
    n = len(samples)
    if n < tol.stochastic_min_samples:
        note = (
            f"only {n} samples; need ≥{tol.stochastic_min_samples} for binary "
            "success equality — reporting non-authoritative statistical note"
        )
        # Do not fail hard on tiny samples.
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            matched=True,
            statistical=True,
            confidence_note=note,
            detail="insufficient_samples",
        )
    ref_rate = sum(1 for r, _ in samples if r) / n
    cand_rate = sum(1 for _, c in samples if c) / n
    # Wald SE under pooled null for difference of proportions (approx).
    pooled = (ref_rate + cand_rate) / 2.0
    se = sqrt(max(pooled * (1.0 - pooled) * 2.0 / n, 1e-12))
    diff = abs(ref_rate - cand_rate)
    z = diff / se
    matched = z <= tol.stochastic_z
    note = (
        f"n={n} ref_rate={ref_rate:.3f} cand_rate={cand_rate:.3f} "
        f"z={z:.3f} threshold={tol.stochastic_z}"
    )
    return DimensionVerdict(
        dimension=ComparisonDimension.SUCCESS,
        matched=matched,
        statistical=True,
        confidence_note=note,
        detail=None if matched else "success rates diverge beyond tolerance",
    )


def _mapping_close(
    left: dict[str, Any],
    right: dict[str, Any],
    tol: ComparisonTolerances,
) -> bool:
    if set(left) != set(right):
        return False
    for key, lval in left.items():
        rval = right[key]
        if isinstance(lval, int | float) and isinstance(rval, int | float):
            abs_ok = abs(float(lval) - float(rval)) <= tol.numeric_abs
            denom = max(abs(float(lval)), abs(float(rval)), 1e-12)
            rel_ok = abs(float(lval) - float(rval)) / denom <= tol.numeric_rel
            if not (abs_ok or rel_ok):
                return False
        elif lval != rval:
            return False
    return True
