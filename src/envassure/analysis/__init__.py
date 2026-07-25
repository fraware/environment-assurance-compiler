"""Static analysis, coverage, and semantic mutation for Environment IR."""

from __future__ import annotations

from envassure.analysis.coverage import (
    CoverageDimensions,
    CoverageReport,
    CoverageTrace,
    compute_coverage,
)
from envassure.analysis.mutation import MutationCategory, apply_mutation, list_mutation_scopes
from envassure.analysis.static import StaticAnalysisResult, analyze_world

__all__ = [
    "CoverageDimensions",
    "CoverageReport",
    "CoverageTrace",
    "MutationCategory",
    "StaticAnalysisResult",
    "analyze_world",
    "apply_mutation",
    "compute_coverage",
    "list_mutation_scopes",
]
