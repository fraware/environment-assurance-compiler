"""Differential validation: connectors, probes, comparison, minimization."""

from __future__ import annotations

from envassure.differential.compare import (
    ComparisonDimension,
    ComparisonResult,
    ComparisonTolerances,
    compare_outcomes,
)
from envassure.differential.connector import (
    FileBackedSimulatorConnector,
    InMemoryReferenceConnector,
    LocalHttpStubConnector,
    ProbeOutcome,
    RecordedFixtureConnector,
    ReferenceConnector,
    SubprocessReferenceConnector,
)
from envassure.differential.minimize import (
    MinimizationResult,
    ReductionStep,
    minimize_counterexample,
)
from envassure.differential.probes import Probe, ProbeKind, plan_probes

__all__ = [
    "ComparisonDimension",
    "ComparisonResult",
    "ComparisonTolerances",
    "FileBackedSimulatorConnector",
    "InMemoryReferenceConnector",
    "LocalHttpStubConnector",
    "MinimizationResult",
    "PostgresReferenceConnector",
    "Probe",
    "ProbeKind",
    "ProbeOutcome",
    "RecordedFixtureConnector",
    "ReductionStep",
    "ReferenceConnector",
    "SubprocessReferenceConnector",
    "compare_outcomes",
    "minimize_counterexample",
    "plan_probes",
]


def __getattr__(name: str) -> object:
    if name == "PostgresReferenceConnector":
        from envassure.postgres import PostgresReferenceConnector

        return PostgresReferenceConnector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
