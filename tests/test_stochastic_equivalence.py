"""Regression tests for stochastic equivalence verdict semantics."""

from __future__ import annotations

import pytest

from envassure.differential.compare import (
    ComparisonTolerances,
    VerdictStatus,
    _paired_rate_difference_ci,
    _statistical_success,
)


def test_identical_paired_samples_establish_equivalence_with_nonzero_uncertainty() -> None:
    samples = [(i % 2 == 0, i % 2 == 0) for i in range(100)]
    difference, lower, upper, _alpha = _paired_rate_difference_ci(samples, z=1.96)
    assert difference == 0.0
    assert lower < 0.0 < upper
    assert lower >= -0.05
    assert upper <= 0.05

    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.MATCH
    assert "method=bonferroni-clopper-pearson" in (verdict.confidence_note or "")


def test_perfect_concordance_at_small_n_does_not_collapse_uncertainty() -> None:
    samples = [(True, True)] * 30
    difference, lower, upper, _alpha = _paired_rate_difference_ci(samples, z=1.96)
    assert difference == 0.0
    assert lower < -0.05
    assert upper > 0.05

    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.INDETERMINATE


def test_point_estimate_equality_does_not_prove_equivalence() -> None:
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
    samples = [(False, True)] * 2 + [(True, True)] * 99 + [(False, False)] * 99
    difference, lower, upper, _alpha = _paired_rate_difference_ci(samples, z=1.96)
    assert difference == pytest.approx(0.01)
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


def test_vacuous_binary_equivalence_margin_is_indeterminate() -> None:
    samples = [(True, True)] * 100
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=1.0),
    )
    assert verdict.status is VerdictStatus.INDETERMINATE
    assert verdict.detail == "invalid_equivalence_margin"


def test_nonpositive_minimum_sample_configuration_is_indeterminate() -> None:
    samples = [(True, True)] * 100
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(stochastic_min_samples=0, equivalence_margin=0.05),
    )
    assert verdict.status is VerdictStatus.INDETERMINATE
    assert verdict.detail == "invalid_minimum_samples"


def test_nan_confidence_configuration_is_indeterminate() -> None:
    samples = [(True, True)] * 100
    verdict = _statistical_success(
        samples,
        ComparisonTolerances(
            stochastic_min_samples=30,
            stochastic_z=float("nan"),
            equivalence_margin=0.05,
        ),
    )
    assert verdict.status is VerdictStatus.INDETERMINATE
    assert verdict.detail == "invalid_confidence_critical_value"
