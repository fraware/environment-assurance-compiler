"""Regression tests for stochastic equivalence verdict semantics."""

from __future__ import annotations

from envassure.differential.compare import (
    ComparisonTolerances,
    VerdictStatus,
    _paired_rate_difference_ci,
    _statistical_success,
)


def test_identical_paired_samples_establish_equivalence() -> None:
    samples = [(i % 2 == 0, i % 2 == 0) for i in range(100)]
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.MATCH
    assert "paired_ci=[0.0000,0.0000]" in (verdict.confidence_note or "")


def test_point_estimate_equality_does_not_prove_equivalence() -> None:
    # Equal aggregate rates but substantial paired discordance. The point
    # estimate is zero, yet uncertainty is wider than the +/-5% margin.
    samples = (
        [(True, False)] * 10 + [(False, True)] * 10 + [(True, True)] * 40 + [(False, False)] * 40
    )
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.INDETERMINATE
    assert verdict.detail == "paired confidence interval overlaps declared equivalence margin"


def test_small_well_estimated_difference_can_establish_equivalence() -> None:
    samples = [(False, True)] * 4 + [(True, True)] * 98 + [(False, False)] * 98
    difference, lower, upper, _se = _paired_rate_difference_ci(samples, z=1.96)
    assert difference == 0.02
    assert lower >= -0.05
    assert upper <= 0.05

    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.MATCH


def test_clear_rate_divergence_is_mismatch() -> None:
    samples = [(False, True)] * 100
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.MISMATCH


def test_underpowered_equivalence_is_indeterminate() -> None:
    samples = [(True, True)] * 20
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.INDETERMINATE
    assert verdict.detail == "insufficient_samples"
