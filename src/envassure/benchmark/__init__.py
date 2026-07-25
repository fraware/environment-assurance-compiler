"""Hidden-reference / generator benchmark harness (EAC-030).

Runs offline against local fixture oracles. Differential engine types are
imported only for optional live runs; fixture mode needs no connectors.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash

MetricName = Literal[
    "transition_agreement",
    "auth_agreement",
    "failure_agreement",
    "observation_agreement",
    "leakage",
    "solvability",
    "diff_match",
    "solve_rate",
    "verify_fpr",
]


class AblationConfig(BaseModel):
    """Research ablation toggles — does not affect release packs by default."""

    model_config = ConfigDict(extra="forbid")

    name: str = "default"
    disable_static_analysis: bool = False
    disable_differential: bool = False
    disable_mutation_testing: bool = False
    use_model_judged_verifiers: bool = False
    hidden_reference: bool = True
    max_probes: int = 100
    seed: int = 0
    notes: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    family: Literal["hidden_reference", "open_reference", "ablation", "generator"] = (
        "hidden_reference"
    )
    world_ref: str
    hidden_oracle_digest: str | None = None
    fixture_path: str | None = None
    metrics: list[str] = Field(
        default_factory=lambda: [
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ]
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str = "envassure-beta-v1"
    cases: list[BenchmarkCase] = Field(default_factory=list)
    ablation: AblationConfig = Field(default_factory=AblationConfig)

    def add_hidden_reference(
        self,
        case_id: str,
        *,
        world_ref: str,
        hidden_oracle_digest: str,
        fixture_path: str | None = None,
    ) -> None:
        self.cases.append(
            BenchmarkCase(
                case_id=case_id,
                family="hidden_reference",
                world_ref=world_ref,
                hidden_oracle_digest=hidden_oracle_digest,
                fixture_path=fixture_path,
            )
        )


class OracleEpisode(BaseModel):
    """One fixture episode comparing candidate vs hidden oracle."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    action_id: str | None = None
    oracle: dict[str, Any] = Field(default_factory=dict)
    candidate: dict[str, Any] = Field(default_factory=dict)
    solvable: bool | None = None
    leaked_paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FixtureOracle(BaseModel):
    """Local fixture oracle bundle (no network, no live connectors)."""

    model_config = ConfigDict(extra="forbid")

    oracle_id: str
    environment_id: str | None = None
    episodes: list[OracleEpisode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class MetricScores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transition_agreement: float | None = None
    auth_agreement: float | None = None
    failure_agreement: float | None = None
    observation_agreement: float | None = None
    leakage: float | None = None
    solvability: float | None = None
    diff_match: float | None = None
    solve_rate: float | None = None
    verify_fpr: float | None = None
    extras: dict[str, float] = Field(default_factory=dict)


class BenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suite_id: str | None = None
    case_id: str | None = None
    environment_id: str | None = None
    episode_count: int = 0
    metrics: MetricScores = Field(default_factory=MetricScores)
    ablation: AblationConfig = Field(default_factory=AblationConfig)
    oracle_digest: str | None = None
    skipped: bool = False
    reason: str | None = None
    details: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class BenchmarkProbeResult:
    probe_id: str
    matched: bool
    failing_dimensions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HiddenReferenceBenchmark:
    """Optional live connector run — prefer fixture harness for offline CI."""

    world: Any
    reference: Any
    candidate_factory: Callable[[], Any]
    ablation: AblationConfig | None = None

    def run(self, *, max_probes: int | None = None) -> dict[str, Any]:
        from envassure.differential.compare import compare_outcomes
        from envassure.differential.probes import plan_probes

        ablation = self.ablation or AblationConfig()
        if ablation.disable_differential:
            return {
                "skipped": True,
                "reason": "ablation disable_differential",
                "results": [],
            }
        limit = max_probes if max_probes is not None else ablation.max_probes
        probes = plan_probes(self.world, max_probes=limit)
        candidate = self.candidate_factory()
        self.reference.reset(seed=ablation.seed)
        candidate.reset(seed=ablation.seed)
        results: list[BenchmarkProbeResult] = []
        for probe in probes:
            ref_out = self.reference.execute(probe.id, probe.action_id, probe.payload)
            cand_out = candidate.execute(probe.id, probe.action_id, probe.payload)
            comparison = compare_outcomes(ref_out, cand_out, world=self.world)
            results.append(
                BenchmarkProbeResult(
                    probe_id=probe.id,
                    matched=comparison.matched,
                    failing_dimensions=[d.value for d in comparison.failing_dimensions],
                )
            )
        # comparison.matched is True only for overall MATCH (indeterminate never passes).
        matched = sum(1 for r in results if r.matched)
        return {
            "environment_id": self.world.environment_id,
            "probe_count": len(results),
            "matched": matched,
            "mismatched": len(results) - matched,
            "ablation": ablation.model_dump(mode="json"),
            "hidden_reference": ablation.hidden_reference,
            "results": [
                {
                    "probe_id": r.probe_id,
                    "matched": r.matched,
                    "failing_dimensions": r.failing_dimensions,
                }
                for r in results
            ],
        }


def load_fixture_oracle(path: Path) -> FixtureOracle:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return FixtureOracle.model_validate(data)


def score_episodes(
    episodes: Sequence[OracleEpisode],
    *,
    metrics: Sequence[str] | None = None,
) -> MetricScores:
    """Compute agreement / leakage / solvability metrics over fixture episodes."""
    wanted = set(
        metrics
        or [
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "observation_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ]
    )
    if not episodes:
        return MetricScores()

    def _rate(predicate: Callable[[OracleEpisode], bool | None]) -> float:
        values = [predicate(ep) for ep in episodes]
        usable = [v for v in values if v is not None]
        if not usable:
            return 0.0
        return sum(1 for v in usable if v) / len(usable)

    scores = MetricScores()
    if "transition_agreement" in wanted:
        scores.transition_agreement = _rate(
            lambda ep: _agree(ep.oracle, ep.candidate, ("state", "success", "transition"))
        )
    if "auth_agreement" in wanted:
        scores.auth_agreement = _rate(
            lambda ep: _agree(ep.oracle, ep.candidate, ("authorized", "authorization", "auth"))
        )
    if "failure_agreement" in wanted:
        scores.failure_agreement = _rate(
            lambda ep: _agree(ep.oracle, ep.candidate, ("failure", "failure_code", "error"))
        )
    if "observation_agreement" in wanted:
        scores.observation_agreement = _rate(
            lambda ep: _agree(ep.oracle, ep.candidate, ("observation", "obs"))
        )
    if "diff_match" in wanted:
        scores.diff_match = _rate(lambda ep: ep.oracle == ep.candidate)
    if "leakage" in wanted:
        # Fraction of episodes that leak hidden paths (lower is better).
        leaked = sum(1 for ep in episodes if ep.leaked_paths)
        scores.leakage = leaked / len(episodes)
    if "solvability" in wanted or "solve_rate" in wanted:
        solvable_eps = [ep for ep in episodes if ep.solvable is not None]
        if solvable_eps:
            rate = sum(1 for ep in solvable_eps if ep.solvable) / len(solvable_eps)
            if "solvability" in wanted:
                scores.solvability = rate
            if "solve_rate" in wanted:
                scores.solve_rate = rate
    if "verify_fpr" in wanted:
        # Fixture may encode false-positive verifications under metadata.
        fps = [
            bool(ep.metadata.get("verify_false_positive"))
            for ep in episodes
            if "verify_false_positive" in ep.metadata
        ]
        scores.verify_fpr = (sum(fps) / len(fps)) if fps else 0.0
    return scores


def run_fixture_benchmark(
    oracle: FixtureOracle | Path,
    *,
    ablation: AblationConfig | None = None,
    case_id: str | None = None,
    suite_id: str | None = None,
    metrics: Sequence[str] | None = None,
) -> BenchmarkReport:
    """Offline hidden-reference / generator benchmark against a fixture oracle."""
    abl = ablation or AblationConfig(name="fixture", hidden_reference=True)
    if abl.disable_differential and abl.metadata.get("require_differential"):
        return BenchmarkReport(
            suite_id=suite_id,
            case_id=case_id,
            skipped=True,
            reason="ablation disable_differential",
            ablation=abl,
        )
    fixture = oracle if isinstance(oracle, FixtureOracle) else load_fixture_oracle(oracle)
    if abl.max_probes and len(fixture.episodes) > abl.max_probes:
        episodes = list(fixture.episodes[: abl.max_probes])
    else:
        episodes = list(fixture.episodes)
    scores = score_episodes(episodes, metrics=metrics)
    details = [
        {
            "episode_id": ep.episode_id,
            "action_id": ep.action_id,
            "matched": ep.oracle == ep.candidate,
            "leaked_paths": list(ep.leaked_paths),
            "solvable": ep.solvable,
        }
        for ep in episodes
    ]
    return BenchmarkReport(
        suite_id=suite_id,
        case_id=case_id,
        environment_id=fixture.environment_id,
        episode_count=len(episodes),
        metrics=scores,
        ablation=abl,
        oracle_digest=fixture.content_digest(),
        details=details,
        metadata={"oracle_id": fixture.oracle_id, **fixture.metadata},
    )


def run_ablation_sweep(
    oracle: FixtureOracle | Path,
    ablations: Sequence[AblationConfig] | None = None,
    *,
    case_id: str | None = None,
) -> list[BenchmarkReport]:
    """Run the same fixture under each ablation config."""
    configs = list(ablations or default_ablations())
    return [
        run_fixture_benchmark(oracle, ablation=cfg, case_id=case_id or cfg.name) for cfg in configs
    ]


def default_beta_suite() -> BenchmarkSuite:
    suite = BenchmarkSuite()
    suite.add_hidden_reference(
        "counter-hidden",
        world_ref="examples/counter",
        hidden_oracle_digest="pending",
        fixture_path="benchmarks/fixtures/counter_oracle.json",
    )
    suite.add_hidden_reference(
        "auth-hidden",
        world_ref="examples/auth",
        hidden_oracle_digest="pending",
        fixture_path="benchmarks/fixtures/auth_oracle.json",
    )
    suite.add_hidden_reference(
        "inventory-hidden",
        world_ref="examples/inventory",
        hidden_oracle_digest="pending",
        fixture_path="benchmarks/fixtures/inventory_oracle.json",
    )
    return suite


def default_ablations() -> list[AblationConfig]:
    return [
        AblationConfig(name="full"),
        AblationConfig(name="no_static", disable_static_analysis=True),
        AblationConfig(name="no_diff", disable_differential=True),
        AblationConfig(name="hidden_ref", hidden_reference=True, max_probes=128),
    ]


def make_hidden_benchmark(
    world: Any,
    *,
    reference_scripts: Mapping[str, Any],
    candidate_scripts: Mapping[str, Any] | None = None,
    ablation: AblationConfig | None = None,
) -> HiddenReferenceBenchmark:
    from envassure.differential.connector import InMemoryReferenceConnector, ProbeOutcome

    scripts: dict[str, ProbeOutcome | dict[str, Any]] = dict(reference_scripts)
    ref = InMemoryReferenceConnector(connector_name="hidden_reference", scripts=scripts)
    cand_data: dict[str, ProbeOutcome | dict[str, Any]] = (
        dict(candidate_scripts) if candidate_scripts is not None else dict(scripts)
    )

    def factory() -> InMemoryReferenceConnector:
        return InMemoryReferenceConnector(connector_name="candidate", scripts=cand_data)

    return HiddenReferenceBenchmark(
        world=world,
        reference=ref,
        candidate_factory=factory,
        ablation=ablation or AblationConfig(name="hidden_ref", hidden_reference=True),
    )


def write_benchmark_report(report: BenchmarkReport, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _agree(oracle: dict[str, Any], candidate: dict[str, Any], keys: Sequence[str]) -> bool | None:
    present = [k for k in keys if k in oracle or k in candidate]
    if not present:
        return None
    return all(oracle.get(k) == candidate.get(k) for k in present)


def __getattr__(name: str) -> Any:
    if name in {
        "WORKFLOW_IDS",
        "WORKFLOW_SPECS",
        "build_workflow_oracle",
        "default_concealed_suite",
        "oracle_digest_for",
        "preregistered_stats_note",
        "run_concealed_suite",
        "write_workflow_fixture",
        "write_workflow_manifest",
    }:
        from envassure.benchmark import workflows as _workflows

        return getattr(_workflows, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
