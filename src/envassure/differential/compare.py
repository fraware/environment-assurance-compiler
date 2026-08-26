"""Typed comparison dimensions and four-state differential verdicts (R12)."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from math import exp, fsum, lgamma, log, log1p
from statistics import NormalDist
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
    # Backward-compatible confidence-level control. The value is converted
    # to a two-sided nominal alpha for exact binomial bounds; it is not used
    # as a Wald multiplier. 1.96 corresponds approximately to 95%.
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


def _binomial_probability_sum(
    start: int,
    stop: int,
    n: int,
    p: float,
) -> float:
    """Return a numerically stable sum of Binomial(n, p) probabilities."""
    if start > stop:
        return 0.0
    if p <= 0.0:
        return 1.0 if start <= 0 <= stop else 0.0
    if p >= 1.0:
        return 1.0 if start <= n <= stop else 0.0

    log_p = log(p)
    log_q = log1p(-p)
    log_n_factorial = lgamma(n + 1)
    log_terms = [
        log_n_factorial
        - lgamma(k + 1)
        - lgamma(n - k + 1)
        + k * log_p
        + (n - k) * log_q
        for k in range(start, stop + 1)
    ]
    max_log = max(log_terms)
    total = exp(max_log) * fsum(exp(value - max_log) for value in log_terms)
    return min(1.0, total)


def _binomial_cdf(k: int, n: int, p: float) -> float:
    """Binomial CDF, summing the numerically smaller tail when possible."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    if k < n * p:
        return _binomial_probability_sum(0, k, n, p)
    upper = _binomial_probability_sum(k + 1, n, n, p)
    return max(0.0, 1.0 - upper)


def _binomial_upper_tail(k: int, n: int, p: float) -> float:
    """P[X >= k] for X ~ Binomial(n, p), with stable tail selection."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    if k > n * p:
        return _binomial_probability_sum(k, n, n, p)
    lower = _binomial_probability_sum(0, k - 1, n, p)
    return max(0.0, 1.0 - lower)


def _solve_probability(
    target: float,
    fn: Callable[[float], float],
    *,
    increasing: bool,
) -> float:
    """Invert a monotone probability function on [0, 1] by bisection."""
    lower = 0.0
    upper = 1.0
    for _ in range(70):
        midpoint = (lower + upper) / 2.0
        value = fn(midpoint)
        if increasing:
            if value < target:
                lower = midpoint
            else:
                upper = midpoint
        elif value > target:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def _clopper_pearson_interval(
    successes: int,
    n: int,
    *,
    alpha: float,
) -> tuple[float, float]:
    """Equal-tailed Clopper-Pearson interval for a binomial proportion."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= successes <= n:
        raise ValueError("successes must be between 0 and n")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")

    tail = alpha / 2.0
    lower = (
        0.0
        if successes == 0
        else _solve_probability(
            tail,
            lambda p: _binomial_upper_tail(successes, n, p),
            increasing=True,
        )
    )
    upper = (
        1.0
        if successes == n
        else _solve_probability(
            tail,
            lambda p: _binomial_cdf(successes, n, p),
            increasing=False,
        )
    )
    return lower, upper


def _paired_rate_difference_ci(
    samples: list[tuple[bool, bool]],
    *,
    z: float,
) -> tuple[float, float, float, float]:
    """Conservative finite-sample CI for candidate-minus-reference success.

    For paired binary outcomes, only discordant cells determine the marginal
    success-rate difference: ``delta = p01 - p10``. Each discordant-cell
    probability is a binomial marginal of the four-cell multinomial table.
    We compute Clopper-Pearson intervals for both probabilities and allocate
    half of the total error budget to each interval. Bonferroni therefore
    gives simultaneous coverage of at least ``1 - alpha``; subtracting the
    simultaneous bounds yields a conservative interval for ``delta``.

    ``z`` is retained for configuration compatibility and converted to the
    corresponding two-sided nominal alpha. It is not used as a Wald
    multiplier.

    Returns ``(difference, lower, upper, nominal_alpha)``.
    """
    n = len(samples)
    if n <= 0:
        raise ValueError("paired samples must be non-empty")
    nominal_alpha = 2.0 * (1.0 - NormalDist().cdf(z))
    if not 0.0 < nominal_alpha < 1.0:
        raise ValueError("stochastic_z does not define a finite confidence level")

    ref_only = sum(1 for reference, candidate in samples if reference and not candidate)
    cand_only = sum(1 for reference, candidate in samples if not reference and candidate)

    marginal_alpha = nominal_alpha / 2.0
    ref_lower, ref_upper = _clopper_pearson_interval(
        ref_only,
        n,
        alpha=marginal_alpha,
    )
    cand_lower, cand_upper = _clopper_pearson_interval(
        cand_only,
        n,
        alpha=marginal_alpha,
    )

    difference = (cand_only - ref_only) / n
    lower = max(-1.0, cand_lower - ref_upper)
    upper = min(1.0, cand_upper - ref_lower)
    return difference, lower, upper, nominal_alpha


def _statistical_success(
    samples: list[tuple[bool, bool]],
    tol: ComparisonTolerances,
) -> DimensionVerdict:
    """Evaluate paired binary equivalence without non-rejection-as-proof.

    A match requires the entire conservative finite-sample confidence
    interval for the candidate-minus-reference success-rate difference to
    lie inside the preregistered equivalence margin. An interval wholly
    beyond a margin is a mismatch; overlap is indeterminate.
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
    if not 0.0 < tol.equivalence_margin < 1.0:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note=(
                "equivalence_margin must lie strictly inside (0, 1) for binary rate difference"
            ),
            detail="invalid_equivalence_margin",
        )
    if tol.stochastic_min_samples <= 0:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note="stochastic_min_samples must be positive",
            detail="invalid_minimum_samples",
        )
    if not tol.stochastic_z > 0:
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
    try:
        difference, lower, upper, nominal_alpha = _paired_rate_difference_ci(
            samples,
            z=tol.stochastic_z,
        )
    except ValueError as exc:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.INDETERMINATE,
            statistical=True,
            confidence_note=str(exc),
            detail="invalid_confidence_critical_value",
        )

    margin = tol.equivalence_margin
    discordant = sum(1 for reference, candidate in samples if reference != candidate)
    confidence = 1.0 - nominal_alpha
    note = (
        f"n={n} ref_rate={ref_rate:.3f} cand_rate={cand_rate:.3f} "
        f"delta(cand-ref)={difference:.4f} paired_ci=[{lower:.4f},{upper:.4f}] "
        f"margin=[{-margin:.4f},{margin:.4f}] confidence={confidence:.5f} "
        f"method=bonferroni-clopper-pearson discordant={discordant}"
    )

    if lower >= -margin and upper <= margin:
        return DimensionVerdict(
            dimension=ComparisonDimension.SUCCESS,
            status=VerdictStatus.MATCH,
            statistical=True,
            confidence_note=note,
            detail="paired confidence interval contained in declared equivalence region",
        )

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
