"""Multi-dimensional coverage model for dynamic validation (§17.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.ir.models import WorldDefinition


class CoverageDimensions(BaseModel):
    """Declared coverage axes for an environment."""

    model_config = ConfigDict(extra="forbid")

    actions: set[str] = Field(default_factory=set)
    transitions: set[str] = Field(default_factory=set)
    failures: set[str] = Field(default_factory=set)
    observations: set[str] = Field(default_factory=set)

    @classmethod
    def from_world(cls, world: WorldDefinition) -> CoverageDimensions:
        return cls(
            actions={a.id for a in world.actions},
            transitions={t.id for t in world.transitions},
            failures={f.id for f in world.failures},
            observations={o.id for o in world.observations},
        )


class CoverageTrace(BaseModel):
    """Evidence of what a run or suite exercised."""

    model_config = ConfigDict(extra="forbid")

    actions: set[str] = Field(default_factory=set)
    transitions: set[str] = Field(default_factory=set)
    failures: set[str] = Field(default_factory=set)
    observations: set[str] = Field(default_factory=set)

    def merge(self, other: CoverageTrace) -> CoverageTrace:
        return CoverageTrace(
            actions=self.actions | other.actions,
            transitions=self.transitions | other.transitions,
            failures=self.failures | other.failures,
            observations=self.observations | other.observations,
        )


@dataclass(slots=True)
class DimensionCoverage:
    name: str
    covered: set[str]
    total: set[str]

    @property
    def ratio(self) -> float:
        if not self.total:
            return 1.0
        return len(self.covered & self.total) / len(self.total)

    @property
    def missing(self) -> set[str]:
        return self.total - self.covered


@dataclass(slots=True)
class CoverageReport:
    """Multi-dimensional coverage summary (no single scalar grade)."""

    dimensions: dict[str, DimensionCoverage] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            name: {
                "ratio": dim.ratio,
                "covered": sorted(dim.covered & dim.total),
                "missing": sorted(dim.missing),
                "total": len(dim.total),
            }
            for name, dim in self.dimensions.items()
        }

    def overall_complete(self) -> bool:
        return all(dim.missing == set() for dim in self.dimensions.values())


def compute_coverage(
    world: WorldDefinition,
    trace: CoverageTrace | None = None,
    *,
    traces: list[CoverageTrace] | None = None,
) -> CoverageReport:
    """Compute coverage across actions, transitions, failures, and observations."""
    declared = CoverageDimensions.from_world(world)
    merged = CoverageTrace()
    if trace is not None:
        merged = merged.merge(trace)
    if traces:
        for item in traces:
            merged = merged.merge(item)

    report = CoverageReport()
    mapping = {
        "actions": (merged.actions, declared.actions),
        "transitions": (merged.transitions, declared.transitions),
        "failures": (merged.failures, declared.failures),
        "observations": (merged.observations, declared.observations),
    }
    for name, (covered, total) in mapping.items():
        report.dimensions[name] = DimensionCoverage(
            name=name,
            covered=set(covered),
            total=set(total),
        )
    if world.determinism == "statistical":
        report.notes.append(
            "Statistical environments require distributional coverage, not binary hit rates."
        )
    return report
