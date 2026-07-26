"""Reconciliation package exports."""

from __future__ import annotations

from envassure.reconciliation.cegr import (
    FIXTURE_AMBIGUITY_ALIASES,
    BranchApplyRecord,
    CegrLoopResult,
    CegrResult,
    CounterexampleIntake,
    RefinementGeneration,
    RegressionMutationReport,
    ReplayObservation,
    TransitionPatchProposal,
    apply_cegr,
    counterexample_from_mapping,
    list_refinement_generations,
    persist_refinement_generation,
    resolve_ambiguity_alias,
    run_cegr_loop,
)
from envassure.reconciliation.engine import (
    ReconciliationResult,
    ambiguity_id,
    project_source_precedence,
    reconcile,
)

__all__ = [
    "FIXTURE_AMBIGUITY_ALIASES",
    "BranchApplyRecord",
    "CegrLoopResult",
    "CegrResult",
    "CounterexampleIntake",
    "ReconciliationResult",
    "RefinementGeneration",
    "RegressionMutationReport",
    "ReplayObservation",
    "TransitionPatchProposal",
    "ambiguity_id",
    "apply_cegr",
    "counterexample_from_mapping",
    "list_refinement_generations",
    "persist_refinement_generation",
    "project_source_precedence",
    "reconcile",
    "resolve_ambiguity_alias",
    "run_cegr_loop",
]
