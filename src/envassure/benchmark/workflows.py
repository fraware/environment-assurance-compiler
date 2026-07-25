"""Concealed hidden-reference workflows (EAC-R15).

Three offline workflows with ≥100 curated probes plus generated probes each.
Oracle logic is intentionally local to this module so candidates cannot read
fixture answers as a side channel when using generated probes only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.benchmark import (
    AblationConfig,
    BenchmarkCase,
    BenchmarkReport,
    BenchmarkSuite,
    FixtureOracle,
    MetricScores,
    OracleEpisode,
    run_fixture_benchmark,
    score_episodes,
)
from envassure.canonical import canonical_hash
from envassure.runtime.observations import probe_observation_leaks

WorkflowId = Literal[
    "transactional_enterprise",
    "authorization_heavy",
    "stochastic_operational",
]

WORKFLOW_IDS: tuple[WorkflowId, ...] = (
    "transactional_enterprise",
    "authorization_heavy",
    "stochastic_operational",
)

DEFAULT_CURATED = 100
DEFAULT_GENERATED = 100


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: WorkflowId
    environment_id: str
    family: str
    description: str
    curated_count: int = DEFAULT_CURATED
    generated_count: int = DEFAULT_GENERATED
    seed: int = 0
    metrics: list[str] = Field(
        default_factory=lambda: [
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "observation_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ]
    )


WORKFLOW_SPECS: dict[WorkflowId, WorkflowSpec] = {
    "transactional_enterprise": WorkflowSpec(
        workflow_id="transactional_enterprise",
        environment_id="bench.tx.enterprise.v1",
        family="transactional_enterprise",
        description=(
            "Concealed multi-step refund / ledger workflow with idempotency and "
            "retry conflict probes."
        ),
    ),
    "authorization_heavy": WorkflowSpec(
        workflow_id="authorization_heavy",
        environment_id="bench.auth.heavy.v1",
        family="authorization_heavy",
        description=(
            "Concealed multi-tenant approval workflow emphasizing deny-path "
            "preservation and observation separation."
        ),
    ),
    "stochastic_operational": WorkflowSpec(
        workflow_id="stochastic_operational",
        environment_id="bench.ops.stochastic.v1",
        family="stochastic_operational",
        description=(
            "Concealed inventory / fulfillment workflow with categorical branches "
            "and underpowered-sample negative probes."
        ),
        metrics=[
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "observation_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ],
    ),
}


def _stable_int(seed: int, *parts: Any) -> int:
    payload = json.dumps([seed, *parts], sort_keys=True, default=str)
    return int(hashlib.sha256(payload.encode()).hexdigest()[:8], 16)


def build_workflow_oracle(
    workflow_id: WorkflowId | str,
    *,
    curated_count: int = DEFAULT_CURATED,
    generated_count: int = DEFAULT_GENERATED,
    seed: int = 0,
    include_negative: bool = True,
) -> FixtureOracle:
    """Materialize a concealed oracle with curated + generated episodes."""
    wid: WorkflowId
    if workflow_id not in WORKFLOW_SPECS:
        raise KeyError(f"unknown workflow_id: {workflow_id!r}")
    wid = workflow_id  # type: ignore[assignment]
    spec = WORKFLOW_SPECS[wid]
    builder = {
        "transactional_enterprise": _episodes_transactional,
        "authorization_heavy": _episodes_authorization,
        "stochastic_operational": _episodes_stochastic,
    }[wid]
    curated = builder(
        count=curated_count,
        seed=seed,
        kind="curated",
        include_negative=include_negative,
    )
    generated = builder(
        count=generated_count,
        seed=seed + 10_000,
        kind="generated",
        include_negative=include_negative,
    )
    episodes = curated + generated
    return FixtureOracle(
        oracle_id=f"{wid}-hidden-v1",
        environment_id=spec.environment_id,
        episodes=episodes,
        metadata={
            "family": "hidden_reference",
            "workflow_id": wid,
            "curated_count": len(curated),
            "generated_count": len(generated),
            "seed": seed,
            "concealed": True,
            "description": spec.description,
        },
    )


def default_concealed_suite(
    *,
    curated_count: int = DEFAULT_CURATED,
    generated_count: int = DEFAULT_GENERATED,
    seed: int = 0,
) -> BenchmarkSuite:
    suite = BenchmarkSuite(suite_id="envassure-concealed-v1")
    for wid, spec in WORKFLOW_SPECS.items():
        oracle = build_workflow_oracle(
            wid,
            curated_count=curated_count,
            generated_count=generated_count,
            seed=seed,
        )
        suite.cases.append(
            BenchmarkCase(
                case_id=wid,
                family="hidden_reference",
                world_ref=f"benchmark/workflows/{wid}",
                hidden_oracle_digest=oracle.content_digest(),
                fixture_path=f"benchmarks/fixtures/{wid}.json",
                metrics=list(spec.metrics),
                metadata={
                    "curated_count": curated_count,
                    "generated_count": generated_count,
                    "seed": seed,
                    "environment_id": spec.environment_id,
                },
            )
        )
    return suite


def run_concealed_suite(
    *,
    curated_count: int = DEFAULT_CURATED,
    generated_count: int = DEFAULT_GENERATED,
    seed: int = 0,
    max_probes: int | None = None,
) -> list[BenchmarkReport]:
    """Run all three concealed workflows with dimension-separated metrics."""
    reports: list[BenchmarkReport] = []
    abl = AblationConfig(
        name="concealed",
        hidden_reference=True,
        max_probes=max_probes or (curated_count + generated_count),
        seed=seed,
    )
    for wid in WORKFLOW_IDS:
        oracle = build_workflow_oracle(
            wid,
            curated_count=curated_count,
            generated_count=generated_count,
            seed=seed,
        )
        report = run_fixture_benchmark(
            oracle,
            ablation=abl,
            case_id=wid,
            suite_id="envassure-concealed-v1",
            metrics=WORKFLOW_SPECS[wid].metrics,
        )
        # Attach dimension-separated breakdown for research reporting.
        report.metadata = {
            **report.metadata,
            "dimension_metrics": _dimension_breakdown(oracle.episodes),
            "negative_probe_count": sum(
                1 for ep in oracle.episodes if ep.metadata.get("negative")
            ),
            "curated_count": sum(
                1 for ep in oracle.episodes if ep.metadata.get("probe_kind") == "curated"
            ),
            "generated_count": sum(
                1 for ep in oracle.episodes if ep.metadata.get("probe_kind") == "generated"
            ),
        }
        reports.append(report)
    return reports


def write_workflow_fixture(
    workflow_id: WorkflowId | str,
    path: Path,
    *,
    curated_count: int = DEFAULT_CURATED,
    generated_count: int = DEFAULT_GENERATED,
    seed: int = 0,
) -> Path:
    """Persist a materialized oracle fixture (optional; generators are authoritative)."""
    oracle = build_workflow_oracle(
        workflow_id,
        curated_count=curated_count,
        generated_count=generated_count,
        seed=seed,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(oracle.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def write_workflow_manifest(path: Path, *, seed: int = 0) -> Path:
    """Write compact manifests (no full episode dump) for repo fixtures."""
    suite = default_concealed_suite(seed=seed)
    payload = {
        "suite_id": suite.suite_id,
        "seed": seed,
        "curated_count": DEFAULT_CURATED,
        "generated_count": DEFAULT_GENERATED,
        "workflows": [
            {
                "workflow_id": c.case_id,
                "environment_id": c.metadata.get("environment_id"),
                "hidden_oracle_digest": c.hidden_oracle_digest,
                "fixture_path": c.fixture_path,
                "metrics": c.metrics,
            }
            for c in suite.cases
        ],
        "notes": (
            "Episodes are generated by envassure.benchmark.workflows.build_workflow_oracle; "
            "digests pin the concealed oracle without shipping answer keys as the "
            "sole evaluation path."
        ),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _dimension_breakdown(episodes: list[OracleEpisode]) -> dict[str, float]:
    scores: MetricScores = score_episodes(episodes)
    return {
        k: v
        for k, v in scores.model_dump(mode="json").items()
        if isinstance(v, int | float) and v is not None
    }


def _episodes_transactional(
    *,
    count: int,
    seed: int,
    kind: str,
    include_negative: bool,
) -> list[OracleEpisode]:
    episodes: list[OracleEpisode] = []
    for i in range(count):
        n = _stable_int(seed, kind, i)
        action = ("submit_refund", "confirm", "retry", "observe")[n % 4]
        authorized = (n % 7) != 0
        success = authorized and (n % 5) != 0
        failure = None if success else ("forbidden" if not authorized else "timeout")
        oracle = {
            "success": success,
            "authorized": authorized,
            "failure": failure,
            "state": {"ledger": n % 11, "idempotency_key": f"k-{n % 50}"},
            "retry": "exponential" if failure == "timeout" else "none",
        }
        candidate = dict(oracle)
        negative = False
        leaked: list[str] = []
        if include_negative and (n % 17 == 0):
            # Intentional candidate mismatch / leak — published negative result.
            negative = True
            candidate = {
                **oracle,
                "success": True,
                "failure": None,
                "state": {**oracle["state"], "internal_risk_score": 0.9},
            }
            leaked = ["internal_risk_score"]
        elif include_negative and (n % 19 == 0):
            negative = True
            candidate = {**oracle, "authorized": True, "success": True, "failure": None}
        episodes.append(
            OracleEpisode(
                episode_id=f"tx-{kind}-{i:04d}",
                action_id=action,
                oracle=oracle,
                candidate=candidate,
                solvable=success,
                leaked_paths=leaked,
                metadata={
                    "probe_kind": kind,
                    "negative": negative,
                    "workflow": "transactional_enterprise",
                    "verify_false_positive": negative and bool(leaked),
                },
            )
        )
    return episodes


def _episodes_authorization(
    *,
    count: int,
    seed: int,
    kind: str,
    include_negative: bool,
) -> list[OracleEpisode]:
    episodes: list[OracleEpisode] = []
    roles = ("requester", "approver", "auditor", "admin")
    for i in range(count):
        n = _stable_int(seed, kind, i)
        role = roles[n % len(roles)]
        action = ("submit", "approve", "deny", "observe")[n % 4]
        authorized = role in {"approver", "admin"} if action in {"approve", "deny"} else True
        if action == "observe":
            authorized = True
        success = authorized
        failure = None if success else "forbidden"
        oracle_obs = {"request_status": ("pending", "approved", "denied")[n % 3]}
        if role == "approver":
            oracle_obs = {**oracle_obs, "requester_id": f"u-{n % 20}"}
        # Missing/unknown projection actors must observe empty (never full state).
        missing_projection = role == "auditor" and action == "observe" and (n % 23 == 0)
        if missing_projection:
            oracle_obs = {}
        oracle = {
            "success": success,
            "authorized": authorized,
            "failure": failure,
            "authorization": authorized,
            "observation": oracle_obs,
        }
        candidate = dict(oracle)
        candidate["observation"] = dict(oracle_obs)
        leaked: list[str] = []
        negative = False
        if missing_projection and include_negative and (n % 2 == 0):
            # Fail-open regression: candidate leaks full authoritative state.
            negative = True
            candidate = {
                **oracle,
                "observation": {
                    "request_status": oracle_obs.get("request_status", "pending")
                    if oracle_obs
                    else "pending",
                    "requester_id": f"u-{n % 20}",
                    "approver_id": f"hidden-{n}",
                },
            }
            leaked = probe_observation_leaks(
                candidate["observation"],
                missing_or_unknown_projection=True,
            )
        elif include_negative and (n % 13 == 0):
            negative = True
            candidate = {
                **oracle,
                "observation": {**oracle_obs, "approver_id": f"hidden-{n}"},
            }
            leaked = ["approver_id"]
        elif include_negative and action in {"approve", "deny"} and (n % 11 == 0):
            # Fail-open regression: candidate allows without role.
            negative = True
            candidate = {
                **oracle,
                "authorized": True,
                "success": True,
                "failure": None,
            }
        episodes.append(
            OracleEpisode(
                episode_id=f"auth-{kind}-{i:04d}",
                action_id=action,
                oracle=oracle,
                candidate=candidate,
                solvable=success,
                leaked_paths=leaked,
                metadata={
                    "probe_kind": kind,
                    "negative": negative,
                    "workflow": "authorization_heavy",
                    "role": role,
                    "missing_projection": missing_projection,
                    "verify_false_positive": negative and bool(leaked),
                },
            )
        )
    return episodes


def _episodes_stochastic(
    *,
    count: int,
    seed: int,
    kind: str,
    include_negative: bool,
) -> list[OracleEpisode]:
    episodes: list[OracleEpisode] = []
    for i in range(count):
        n = _stable_int(seed, kind, i)
        action = ("fulfill", "replenish", "tick", "observe")[n % 4]
        stockout = (n % 4) == 0 and action == "fulfill"
        success = not stockout
        failure = "stockout" if stockout else None
        on_hand = max(0, 10 - (n % 9) - (1 if stockout else 0))
        oracle = {
            "success": success,
            "authorized": bool(action != "replenish" or (n % 3)),
            "failure": failure if success or stockout else "forbidden",
            "state": {"on_hand": on_hand, "backlog": n % 5},
            "observation": {"on_hand": on_hand},
            "sample_size": 5 + (n % 40),
        }
        if action == "replenish" and not oracle["authorized"]:
            oracle["success"] = False
            oracle["failure"] = "forbidden"
        candidate = {
            "success": oracle["success"],
            "authorized": oracle["authorized"],
            "failure": oracle["failure"],
            "state": dict(oracle["state"]),
            "observation": dict(oracle["observation"]),
            "sample_size": oracle["sample_size"],
        }
        leaked: list[str] = []
        negative = False
        if include_negative and oracle["sample_size"] < 30 and (n % 9 == 0):
            # Underpowered stochastic evidence must not count as match.
            negative = True
            candidate = {
                **candidate,
                "success": True,
                "failure": None,
                "metadata_note": "underpowered_treated_as_match_bug",
            }
            candidate["state"] = {**candidate["state"], "true_fill_rate": 1.0}
            leaked = ["true_fill_rate"]
        elif include_negative and (n % 15 == 0):
            negative = True
            candidate = {
                **candidate,
                "observation": {**candidate["observation"], "true_fill_rate": 0.99},
            }
            leaked = ["true_fill_rate"]
        episodes.append(
            OracleEpisode(
                episode_id=f"ops-{kind}-{i:04d}",
                action_id=action,
                oracle=oracle,
                candidate=candidate,
                solvable=oracle["success"],
                leaked_paths=leaked,
                metadata={
                    "probe_kind": kind,
                    "negative": negative,
                    "workflow": "stochastic_operational",
                    "underpowered": oracle["sample_size"] < 30,
                    "verify_false_positive": negative and bool(leaked),
                },
            )
        )
    return episodes


def oracle_digest_for(workflow_id: WorkflowId | str, *, seed: int = 0) -> str:
    return build_workflow_oracle(workflow_id, seed=seed).content_digest()


def preregistered_stats_note() -> dict[str, Any]:
    """Preregistered metric dimensions (no composite leaderboard)."""
    return {
        "dimensions": [
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "observation_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ],
        "rules": [
            "Report each dimension separately; do not average into a fidelity score.",
            "Indeterminate / underpowered stochastic probes are non-pass.",
            "Negative probes (intentional mismatches/leaks) must remain visible.",
            "Hidden-reference digests pin oracles; do not tune to fixture answers.",
        ],
        "suite_digest_seed0": canonical_hash(
            {
                wid: oracle_digest_for(wid, seed=0)
                for wid in WORKFLOW_IDS
            }
        ),
    }
