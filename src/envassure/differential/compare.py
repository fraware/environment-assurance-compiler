"""Typed comparison dimensions and four-state differential verdicts (R12)."""

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


class VerdictStatus(StrEnum):
    """Four-state differential verdict — never treat missing evidence as match."""

    MATCH = "match"
    MISMATCH = "mismatch"
    INDETERMINATE = "indeterminate"
    NOT_APPLICABLE = "not_applicable"


class ComparisonTolerances(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latency_ms: float = 50.0
    numeric_abs: float = 1e-6
    numeric_rel: float = 1e-3
    stochastic_min_samples: int = 30
    # Critical value for the paired mean-difference confidence interval.
    # 1.96 corresponds approximately to a two-sided 95% interval.
    stochastic_z: float = 1.96
    # Declared absolute rate-difference margin for stochastic equivalence.
    equivalence_margin: float | None = 0.05


class DimensionVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: ComparisonDimension
    status: VerdictStatus
    detail: str | None = None
    statistical: bool = False
    confidence_note: str | None = None

    @property
    def matched(self) -> bool:
        """Backward-compatible: true only for an authoritative match."""
        return self.status is VerdictStatus.MATCH


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    probe_id: str
    overall_status: VerdictStatus
    verdicts: list[DimensionVerdict] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)

    @property
    def matched(self) -> bool:
        """Overall pass: every required dimension is match or not_applicable.

        Indeterminate or mismatch on any required dimension blocks pass.
        """
        return self.overall_status is VerdictStatus.MATCH

    @property
    def failing_dimensions(self) -> list[ComparisonDimension]:
        return [
            v.dimension
            for v in self.verdicts
            if v.status in {VerdictStatus.MISMATCH, VerdictStatus.INDETERMINATE}
        ]


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
    ``(reference_success, candidate_success)``. Underpowered samples and
    missing dimension evidence yield ``indeterminate``, never ``match``.
    Overall pass requires no mismatch and no indeterminate among required dims.
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
            if verdict.status is VerdictStatus.INDETERMINATE:
                diagnostics.append(
                    make_diagnostic(
                        "EAC7006",
                        reason=verdict.confidence_note or verdict.detail or "underpowered",
                        subject=probe_id,
                        details={"dimension": dim.value},
                    )
                )
            elif verdict.confidence_note:
                diagnostics.append(
                    make_diagnostic(
                        "EAC7002",
                        reason=verdict.confidence_note,
                        subject=probe_id,
                    )
                )
            if verdict.status is VerdictStatus.MISMATCH:
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
            continue

        verdict = _compare_dimension(dim, reference, candidate, tol)
        verdicts.append(verdict)
        if verdict.status is VerdictStatus.MISMATCH:
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
        elif verdict.status is VerdictStatus.INDETERMINATE:
            diagnostics.append(
                make_diagnostic(
                    "EAC7006",
                    reason=verdict.detail or f"dimension {dim.value} indeterminate",
                    subject=probe_id,
                    details={"dimension": dim.value, "detail": verdict.detail},
                )
            )

    overall = _aggregate_status(verdicts)
    return ComparisonResult(
        probe_id=probe_id,
        overall_status=overall,
        verdicts=verdicts,
        diagnostics=diagnostics,
    )


def _aggregate_status(verdicts: list[DimensionVerdict]) -> VerdictStatus:
    if not verdicts:
        return VerdictStatus.NOT_APPLICABLE
    statuses = {v.status for v in verdicts}
    if VerdictStatus.MISMATCH in statuses:
        return VerdictStatus.MISMATCH
    if VerdictStatus.INDETERMINATE in statuses:
        return VerdictStatus.INDETERMINATE
    if statuses <= {VerdictStatus.NOT_APPLICABLE}:
        return VerdictStatus.NOT_APPLICABLE
    # Mix of match and not_applicable → overall match (pass).
    return VerdictStatus.MATCH


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
            status=VerdictStatus.MATCH if ok else VerdictStatus.MISMATCH,
            detail=None if ok else f"ref={reference.success} cand={candidate.success}",
        )
    if dim is ComparisonDimension.OBSERVATION:
        mapping = _mapping_verdict(reference.observation, candidate.observation, tol)
        return DimensionVerdict(
            dimension=dim,
            status=mapping,
            detail=None
            if mapping is VerdictStatus.MATCH
            else "observation maps differ beyond tolerance"
            if mapping is VerdictStatus.MISMATCH
            else "observation evidence incomplete",
        )
    if dim is ComparisonDimension.STATE:
        mapping = _mapping_verdict(reference.state, candidate.state, tol)
        return DimensionVerdict(
            dimension=dim,
            status=mapping,
            detail=None
            if mapping is VerdictStatus.MATCH
            else "state maps differ beyond tolerance"
            if mapping is VerdictStatus.MISMATCH
            else "state evidence incomplete",
        )
    if dim is ComparisonDimension.FAILURE:
        ok = reference.failure_id == candidate.failure_id
        return DimensionVerdict(
            dimension=dim,
            status=VerdictStatus.MATCH if ok else VerdictStatus.MISMATCH,
            detail=None if ok else f"ref={reference.failure_id!r} cand={candidate.failure_id!r}",
        )
    if dim is ComparisonDimension.AUTHORIZATION:
        if reference.authorization_ok is None and candidate.authorization_ok is None:
            return DimensionVerdict(
                dimension=dim,
                status=VerdictStatus.INDETERMINATE,
                detail="authorization evidence unset on both sides",
            )
        if reference.authorization_ok is None or candidate.authorization_ok is None:
            return DimensionVerdict(
                dimension=dim,
                status=VerdictStatus.INDETERMINATE,
                detail=(
                    f"authorization evidence partial: "
                    f"ref={reference.authorization_ok!r} cand={candidate.authorization_ok!r}"
                ),
            )
        ok = reference.authorization_ok == candidate.authorization_ok
        return DimensionVerdict(
            dimension=dim,
            status=VerdictStatus.MATCH if ok else VerdictStatus.MISMATCH,
            detail=None
            if ok
            else f"ref={reference.authorization_ok} cand={candidate.authorization_ok}",
        )
    if dim is ComparisonDimension.RETRY:
        ok = reference.retry_count == candidate.retry_count
        return DimensionVerdict(
            dimension=dim,
            status=VerdictStatus.MATCH if ok else VerdictStatus.MISMATCH,
            detail=None if ok else f"ref={reference.retry_count} cand={candidate.retry_count}",
        )
    if dim is ComparisonDimension.IDEMPOTENCY:
        if reference.idempotent_replay_equal is None and candidate.idempotent_replay_equal is None:
            return DimensionVerdict(
                dimension=dim,
                status=VerdictStatus.INDETERMINATE,
                detail="idempotency evidence unset on both sides",
            )
        if reference.idempotent_replay_equal is None or candidate.idempotent_replay_equal is None:
            return DimensionVerdict(
                dimension=dim,
                status=VerdictStatus.INDETERMINATE,
                detail="idempotency evidence partial",
            )
        ok = reference.idempotent_replay_equal == candidate.idempotent_replay_equal
        return DimensionVerdict(
            dimension=dim,
            status=VerdictStatus.MATCH if ok else VerdictStatus.MISMATCH,
            detail=None if ok else "idempotent replay disagreement",
        )
    if dim is ComparisonDimension.LATENCY:
        if reference.latency_ms is None or candidate.latency_ms is None:
            return DimensionVerdict(
                dimension=dim,
                status=VerdictStatus.INDETERMINATE,
                detail="latency evidence missing",
            )
        ok = abs(reference.latency_ms - candidate.latency_ms) <= tol.latency_ms
        return DimensionVerdict(
            dimension=dim,
            status=VerdictStatus.MATCH if ok else VerdictStatus.MISMATCH,
            detail=None if ok else f"|Δ|={abs(reference.latency_ms - candidate.latency_ms):.3f}ms",
        )
    return DimensionVerdict(dimension=dim, status=VerdictStatus.NOT_APPLICABLE)


def _paired_rate_difference_ci(
    samples: list[tuple[bool, bool]],
    *,
    z: float,
) -> tuple[float, float, float, float]:
    """Asymptotic paired CI for candidate-minus-reference success probability.

    Each paired observation contributes -1, 0, or +1. The variance is therefore
    estimated on the paired differences themselves, preserving pairing instead
    of treating the two success rates as independent samples.

    Returns ``(difference, lower, upper, standard_error)``.
    """
    n = len(samples)
    diffs = [float(candidate) - float(reference) for reference, candidate in samples]
    difference = sum(diffs) / n
    if n <= 1:
        return difference, float("-inf"), float("inf"), float("inf")
    variance = sum((value - difference) ** 2 for value in diffs) / (n - 1)
    standard_error = sqrt(max(variance, 0.0) / n)
    half_width = z * standard_error
    return difference, difference - half_width, difference + half_width, standard_error


def _statistical_success(
    samples: list[tuple[bool, bool]],
    tol: ComparisonTolerances,
) -> DimensionVerdict:
    """Evaluate paired binary equivalence without using non-rejection as proof.

    A match requires the entire paired confidence interval for the
    candidate-minus-reference success-rate difference to lie inside the
    preregistered equivalence margin. If the interval overlaps a margin, the
    result is indeterminate. A mismatch is reported only when the entire
    interval is beyond one equivalence boundary.
    """
    n = len(samples)
    if tol.equivalence_margin is None:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note="equivalence_margin not declared for stochastic comparison",
            detail="missing_equivalence_margin",
        )
    if tol.equivalence_margin <= 0:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note="equivalence_margin must be positive for stochastic comparison",
            detail="invalid_equivalence_margin",
        )
    if tol.stochastic_z <= 0:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note="stochastic_z must be positive for stochastic comparison",
            detail="invalid_confidence_critical_value",
        )
    if n < tol.stochastic_min_samples:
        note = (
            f"only {n} samples; need >= {tol.stochastic_min_samples} for paired "
            "binary success equivalence — indeterminate (not a match)"
        )
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note=note,
            detail="insufficient_samples",
        )

    ref_rate = sum(1 for reference, _ in samples if reference) / n
    cand_rate = sum(1 for _, candidate in samples if candidate) / n
    difference, lower, upper, standard_error = _paired_rate_difference_ci(
        samples,
        z=tol.stochastic_z,
    )
    margin = tol.equivalence_margin
    discordant = sum(1 for reference, candidate in samples if reference != candidate)
    note = (
        f"n={n} ref_rate={ref_rate:.3f} cand_rate={cand_rate:.3f} "
        f"delta(cand-ref)={difference:.4f} paired_ci=[{lower:.4f},{upper:.4f}] "
        f"margin=[{-margin:.4f},{margin:.4f}] se={standard_error:.4f} "
        f"z={tol.stochastic_z:.3f} discordant={discordant}"
    )

    if lower >= -margin and upper <= margin:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.MATCH,
            statistical=True,
            confidence_note=note,
            detail="paired confidence interval contained in declared equivalence region",
        )

    # Only call a mismatch when the confidence interval is wholly outside the
    # declared equivalence region. Overlap is insufficient evidence either way.
    if lower > margin or upper < -margin:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.MISMATCH,
            statistical=True,
            confidence_note=note,
            detail="paired confidence interval lies beyond declared equivalence margin",
        )

    return DimensionVerdict(
        dimension=ComparisonDimension.SUCCESS,
        status=VerdictStatus.INDETERMINATE,
        statistical=True,
        confidence_note=note,
        detail="paired confidence interval overlaps declared equivalence margin",
    )


def _mapping_verdict(
    left: dict[str, Any],
    right: dict[str, Any],
    tol: ComparisonTolerances,
) -> VerdictStatus:
    if not left and not right:
        return VerdictStatus.INDETERMINATE
    if set(left) != set(right):
        return VerdictStatus.MISMATCH
    for key, lval in left.items():
        rval = right[key]
        if isinstance(lval, int | float) and isinstance(rval, int | float):
            abs_ok = abs(float(lval) - float(rval)) <= tol.numeric_abs
            denom = max(abs(float(lval)), abs(float(rval)), 1e-12)
            rel_ok = abs(float(lval) - float(rval)) / denom <= tol.numeric_rel
            if not (abs_ok or rel_ok):
                return VerdictStatus.MISMATCH
        elif lval != rval:
            return VerdictStatus.MISMATCH
    return VerdictStatus.MATCH
