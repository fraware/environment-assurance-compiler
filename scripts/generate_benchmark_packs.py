"""Generate the three public-beta benchmark packs under packs/."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from envassure.api import World, provenance
from envassure.benchmark.pack_format import compute_file_digest, compute_pack_tree_digest
from envassure.ir.models import AmbiguityRecord

ROOT = Path(__file__).resolve().parents[1]
PACKS = ROOT / "packs"
SCHEMA_SRC = ROOT / "schemas" / "benchmark-pack-1.json"

LICENSE_TEXT = """Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Copyright 2026 EnvAssure contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

PACKS_SPEC: list[dict] = [
    {
        "pack_id": "envassure-transactional-refund",
        "workflow_id": "transactional_enterprise",
        "environment_id": "bench.tx.enterprise.v1",
        "domain": "transactional",
        "name": "Transactional Refund Benchmark Pack",
        "description": (
            "Concealed multi-step refund / ledger workflow with idempotency and "
            "retry conflict probes. Maps to concealed suite transactional_enterprise."
        ),
        "hidden_oracle": "de35098a6adb1c28860e9b56ff040a3f8b49fd240ae4a46365094e42d8bef8e8",
        "fixture": "benchmarks/fixtures/transactional_enterprise.json",
        "probe_families": [
            "idempotency",
            "retry_conflict",
            "ledger_consistency",
            "timeout_ambiguity",
        ],
        "unsupported": [
            "retry_after_timeout_without_decision",
            "idempotency_key_unspecified",
            "partial_refund_without_policy",
        ],
        "conflict_subject": "action:submit_refund / retry_behavior",
        "ambiguity_id": "pack-tx-retry-conflict",
    },
    {
        "pack_id": "envassure-delegated-authorization",
        "workflow_id": "authorization_heavy",
        "environment_id": "bench.auth.heavy.v1",
        "domain": "authorization",
        "name": "Delegated Authorization Benchmark Pack",
        "description": (
            "Concealed multi-tenant approval workflow emphasizing deny-path "
            "preservation and observation separation. Maps to authorization_heavy."
        ),
        "hidden_oracle": "f8f4cca23463774f8cf41b292c916e4d2c9696abbf328aec09fdf163b3b1b455",
        "fixture": "benchmarks/fixtures/authorization_heavy.json",
        "probe_families": [
            "deny_path",
            "delegation",
            "observation_separation",
            "role_escalation",
        ],
        "unsupported": [
            "cross_tenant_delegation_without_policy",
            "approver_observation_of_hidden_credentials",
        ],
        "conflict_subject": "action:approve / authority_source",
        "ambiguity_id": "pack-auth-delegation-conflict",
    },
    {
        "pack_id": "envassure-stochastic-operations",
        "workflow_id": "stochastic_operational",
        "environment_id": "bench.ops.stochastic.v1",
        "domain": "operations",
        "name": "Stochastic Operations Benchmark Pack",
        "description": (
            "Concealed inventory / fulfillment workflow with categorical branches "
            "and underpowered-sample negative probes. Maps to stochastic_operational."
        ),
        "hidden_oracle": "b1c1f5d4cc3ac05f24f39063c1427cec28564b0c15f8c848db0ca55e51bc6b54",
        "fixture": "benchmarks/fixtures/stochastic_operational.json",
        "probe_families": [
            "stockout_branch",
            "categorical_transition",
            "underpowered_sample",
            "fulfillment_timeout",
        ],
        "unsupported": [
            "unseeded_stochastic_sampling_as_fidelity_claim",
            "collapsing_dimension_metrics_into_single_score",
        ],
        "conflict_subject": "transition:fulfill / branch_weights",
        "ambiguity_id": "pack-ops-branch-conflict",
    },
]


def _build_world(spec: dict) -> dict:
    world = World(
        environment_id=spec["environment_id"],
        name=spec["name"] + " Baseline",
        description=spec["description"],
        domain=spec["domain"],
    )
    world.definition.task_families = [spec["domain"]]
    world.definition.determinism = "seeded_recorded_externals"
    world.definition.declared_fidelity_level = "EF-0"
    world.definition.known_unsupported_behavior = list(spec["unsupported"])
    world.definition.permissible_uses = ["research", "evaluation", "benchmarking"]
    world.definition.assurance_profile = "benchmark_pack"

    if spec["workflow_id"] == "authorization_heavy":
        world.definition.concurrency_model = "multi_actor"
        world.state(
            "request_status",
            type="enum",
            enum_values=["draft", "pending", "approved", "denied"],
            initial_generator="draft",
        )
        world.state("tenant_id", type="scalar", initial_generator='"t0"')
        world.actor(
            "requester",
            actor_class="requester",
            roles=["user"],
            available_actions=["submit", "observe"],
            observation_projection_id="requester_view",
        )
        world.actor(
            "approver",
            actor_class="approver",
            roles=["approver"],
            available_actions=["approve", "deny", "observe"],
            observation_projection_id="approver_view",
            authority_source="role:approver",
        )
        world.observation(
            "requester_view",
            target_actor_class="requester",
            visible_paths=["request_status"],
            omitted_paths=["tenant_id"],
        )
        world.observation(
            "approver_view",
            target_actor_class="approver",
            visible_paths=["request_status", "tenant_id"],
        )
        world.failure(
            "unauthorized",
            category="authorization",
            description="Caller lacks approver role",
            retryable=False,
        )
        world.action(
            "submit",
            actor_classes=["requester"],
            writes=["request_status"],
            intended_effects=['request_status = "pending"'],
            success_outcomes=["ok"],
            provenance=provenance(source_ids=["pack:sources"]),
        )
        world.action(
            "approve",
            actor_classes=["approver"],
            authorization="role:approver",
            writes=["request_status"],
            intended_effects=['request_status = "approved"'],
            failure_ids=["unauthorized"],
            success_outcomes=["ok"],
        )
        world.action(
            "deny",
            actor_classes=["approver"],
            authorization="role:approver",
            writes=["request_status"],
            intended_effects=['request_status = "denied"'],
            failure_ids=["unauthorized"],
            success_outcomes=["ok"],
        )
        world.action("observe", actor_classes=["requester", "approver"], reads=["request_status"])
        world.transition("t_submit", action_id="submit", events=["request.submitted"])
        world.transition("t_approve", action_id="approve", events=["request.approved"])
        world.transition("t_deny", action_id="deny", events=["request.denied"])
        world.transition("t_observe", action_id="observe", events=["request.observed"])
        world.task(
            "get_approval",
            family="authorization",
            intent="Submit and obtain approval without leaking credentials",
            goal_claims=['request_status == "approved"'],
            actor_assignment={"user": "requester", "reviewer": "approver"},
            horizon=5,
        )
    elif spec["workflow_id"] == "stochastic_operational":
        world.definition.stochasticity_model = "categorical"
        world.state(
            "stock",
            type="resource_counter",
            initial_generator="10",
        )
        world.state(
            "fulfillment_status",
            type="enum",
            enum_values=["idle", "reserved", "shipped", "stockout"],
            initial_generator="idle",
        )
        world.actor(
            "ops",
            actor_class="ops",
            available_actions=["reserve", "ship", "observe"],
        )
        world.action(
            "reserve",
            actor_classes=["ops"],
            writes=["stock", "fulfillment_status"],
            success_outcomes=["ok", "stockout"],
        )
        world.action(
            "ship",
            actor_classes=["ops"],
            writes=["fulfillment_status"],
            success_outcomes=["ok"],
        )
        world.action("observe", actor_classes=["ops"], reads=["stock", "fulfillment_status"])
        world.transition("t_reserve", action_id="reserve", events=["ops.reserved"])
        world.transition("t_ship", action_id="ship", events=["ops.shipped"])
        world.transition("t_observe", action_id="observe", events=["ops.observed"])
        world.task(
            "fulfill_order",
            family="operations",
            intent="Reserve and ship without inventing stock",
            goal_claims=['fulfillment_status == "shipped"'],
            actor_assignment={"operator": "ops"},
            horizon=8,
        )
    else:
        world.state("ledger_balance", type="scalar", initial_generator="100")
        world.state(
            "refund_status",
            type="enum",
            enum_values=["none", "pending", "posted", "conflict"],
            initial_generator="none",
        )
        world.actor(
            "agent",
            actor_class="agent",
            available_actions=["submit_refund", "observe"],
        )
        world.failure(
            "idempotency_conflict",
            category="conflict",
            description="Conflicting retry semantics without decision",
            retryable=True,
        )
        world.action(
            "submit_refund",
            actor_classes=["agent"],
            writes=["ledger_balance", "refund_status"],
            failure_ids=["idempotency_conflict"],
            success_outcomes=["ok"],
            unsupported_semantics=["retry_after_timeout_without_decision"],
            provenance=provenance(source_ids=["pack:openapi", "pack:sop", "pack:trace"]),
        )
        world.action("observe", actor_classes=["agent"], reads=["refund_status"])
        world.transition("t_refund", action_id="submit_refund", events=["refund.submitted"])
        world.transition("t_observe", action_id="observe", events=["refund.observed"])
        world.task(
            "process_refund",
            family="transactional",
            intent="Post a refund without double-spend under timeout",
            goal_claims=['refund_status == "posted"'],
            actor_assignment={"agent": "agent"},
            horizon=6,
        )

    compiled = world.compile()
    amb = AmbiguityRecord(
        id=spec["ambiguity_id"],
        subject=spec["conflict_subject"],
        source_excerpts=["sources/conflict.yaml"],
        conflict_class="semantic_conflict",
        candidate_interpretations=[
            "fail_closed_until_decide",
            "prefer_policy_source",
            "prefer_trace_source",
        ],
        default_prohibition="Do not execute contested semantics without an expert decision.",
        affected_actions=["submit_refund", "approve", "reserve"],
        operational_consequence="Contested path remains open; pack declares unsupported use.",
        required_expert_role="domain_owner",
        status="open",
    )
    compiled.ambiguities.append(amb)
    return compiled.model_dump(mode="json")


def _write_pack(spec: dict) -> Path:
    pack_dir = PACKS / spec["pack_id"]
    if pack_dir.exists():
        shutil.rmtree(pack_dir)

    for dirname in (
        "sources",
        "decisions",
        "world",
        "tasks",
        "probes",
        "baselines",
        "expected-public",
        "schemas",
    ):
        (pack_dir / dirname).mkdir(parents=True)

    world = _build_world(spec)
    baseline_path = pack_dir / "baselines" / "public-baseline.json"
    baseline_path.write_text(json.dumps(world, indent=2) + "\n", encoding="utf-8")
    (pack_dir / "world" / "baseline.json").write_text(
        json.dumps(world, indent=2) + "\n", encoding="utf-8"
    )

    conflict = {
        "id": f"{spec['pack_id']}-conflict",
        "subject": spec["conflict_subject"],
        "sources": [
            {"id": "policy", "claim": "timeouts must fail closed without idempotency key"},
            {"id": "trace", "claim": "retries after timeout were observed succeeding"},
        ],
        "conflict_class": "semantic_conflict",
        "status": "open",
        "note": "Public declaration only; hidden oracle answers remain concealed.",
    }
    (pack_dir / "sources" / "conflict.yaml").write_text(
        yaml.safe_dump(conflict, sort_keys=False), encoding="utf-8"
    )
    (pack_dir / "sources" / "README.md").write_text(
        "# Sources\n\nPublic conflict excerpts only. Hidden oracle episodes are not shipped here.\n",
        encoding="utf-8",
    )

    ambiguity = {
        "id": spec["ambiguity_id"],
        "subject": spec["conflict_subject"],
        "status": "open",
        "required_expert_role": "domain_owner",
        "default_prohibition": "fail_closed",
        "candidate_interpretations": [
            "fail_closed_until_decide",
            "prefer_policy_source",
            "prefer_trace_source",
        ],
    }
    (pack_dir / "decisions" / "open-ambiguity.yaml").write_text(
        yaml.safe_dump(ambiguity, sort_keys=False), encoding="utf-8"
    )

    unsupported = {
        "pack_id": spec["pack_id"],
        "unsupported_uses": list(spec["unsupported"]),
        "note": "Claims that depend on these behaviors must remain indeterminate.",
    }
    (pack_dir / "world" / "unsupported-uses.yaml").write_text(
        yaml.safe_dump(unsupported, sort_keys=False), encoding="utf-8"
    )

    hidden_ref = {
        "kind": "concealed_fixture_oracle",
        "workflow_id": spec["workflow_id"],
        "fixture_path": spec["fixture"],
        "hidden_oracle_digest": spec["hidden_oracle"],
        "generator": "envassure.benchmark.workflows.build_workflow_oracle",
        "note": (
            "Episodes are materialized at evaluation time; answer keys are not "
            "the sole public evaluation path."
        ),
    }
    (pack_dir / "probes" / "hidden-reference.yaml").write_text(
        yaml.safe_dump(hidden_ref, sort_keys=False), encoding="utf-8"
    )

    mutation = {
        "suite_id": f"{spec['pack_id']}-mutations-v1",
        "mutations": [
            {
                "id": "drop_deny_path",
                "target": "authorization|failure",
                "description": "Remove a deny / conflict failure path.",
                "expected_detection": "auth_agreement or failure_agreement regression",
            },
            {
                "id": "leak_hidden_field",
                "target": "observation",
                "description": "Expose an evaluator-only path to agents.",
                "expected_detection": "leakage increase",
            },
            {
                "id": "collapse_metrics",
                "target": "reporting",
                "description": "Collapse dimension metrics into one score.",
                "expected_detection": "pack limitation / verify_fpr",
            },
        ],
    }
    (pack_dir / "probes" / "mutation-suite.yaml").write_text(
        yaml.safe_dump(mutation, sort_keys=False), encoding="utf-8"
    )

    differential = {
        "plan_id": f"{spec['pack_id']}-diff-v1",
        "connector_type": "fixture_oracle",
        "seed": 0,
        "min_probes": 100,
        "dimensions": [
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "observation_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ],
        "commands": [
            f"eac benchmark {spec['fixture']} --json",
            "eac benchmark --concealed --json",
        ],
        "missing_evidence_policy": "indeterminate",
    }
    (pack_dir / "probes" / "differential-plan.yaml").write_text(
        yaml.safe_dump(differential, sort_keys=False), encoding="utf-8"
    )
    (pack_dir / "probes" / "families.yaml").write_text(
        yaml.safe_dump({"families": list(spec["probe_families"])}, sort_keys=False),
        encoding="utf-8",
    )

    task_doc = {
        "tasks": [
            {
                "id": f"{spec['pack_id']}-primary",
                "family": spec["domain"],
                "intent": "Exercise public baseline against concealed oracle",
            }
        ]
    }
    (pack_dir / "tasks" / "primary.yaml").write_text(
        yaml.safe_dump(task_doc, sort_keys=False), encoding="utf-8"
    )

    expected = {
        "metrics_policy": "dimension_separated",
        "forbid_single_score": True,
        "hidden_oracle_digest": spec["hidden_oracle"],
        "public_claims": [
            "structurally_valid_baseline",
            "open_ambiguity_declared",
            "unsupported_uses_declared",
        ],
    }
    (pack_dir / "expected-public" / "metrics.json").write_text(
        json.dumps(expected, indent=2) + "\n", encoding="utf-8"
    )

    shutil.copy2(SCHEMA_SRC, pack_dir / "schemas" / "benchmark-pack-1.json")
    (pack_dir / "LICENSE").write_text(LICENSE_TEXT, encoding="utf-8")
    (pack_dir / "README.md").write_text(
        f"# {spec['name']}\n\n"
        f"{spec['description']}\n\n"
        f"- Pack ID: `{spec['pack_id']}`\n"
        f"- Workflow: `{spec['workflow_id']}`\n"
        f"- Hidden oracle digest: `{spec['hidden_oracle']}`\n\n"
        "## Commands\n\n"
        "```bash\n"
        f"eac pack lint packs/{spec['pack_id']}\n"
        f"eac pack verify packs/{spec['pack_id']}\n"
        f"eac pack inspect packs/{spec['pack_id']} --json\n"
        f"eac pack reproduce packs/{spec['pack_id']} -o /tmp/repro\n"
        f"eac benchmark {spec['fixture']} --json\n"
        "```\n",
        encoding="utf-8",
    )
    (pack_dir / "data-card.md").write_text(
        f"# Data card — {spec['pack_id']}\n\n"
        f"- Domain: {spec['domain']}\n"
        f"- Sensitivity: public\n"
        f"- Licenses: Apache-2.0\n"
        f"- Public components: sources, decisions, baseline world, probes plans\n"
        f"- Hidden components: concealed oracle episodes (digest-pinned)\n"
        f"- Fixture map: `{spec['fixture']}`\n",
        encoding="utf-8",
    )
    (pack_dir / "benchmark-card.md").write_text(
        f"# Benchmark card — {spec['pack_id']}\n\n"
        f"- Metrics: dimension-separated (no single fidelity score)\n"
        f"- Probe families: {', '.join(spec['probe_families'])}\n"
        f"- Includes source conflict, open ambiguity, unsupported-use declaration, "
        f"baseline, mutation suite, and differential plan\n"
        f"- Governance owner: EnvAssure maintainers\n",
        encoding="utf-8",
    )

    baseline_digest = compute_file_digest(baseline_path)
    # Write pack.yaml without pack_tree first, then fill pack_tree.
    manifest = {
        "schema_version": "1",
        "pack_id": spec["pack_id"],
        "version": "0.2.0b1",
        "name": spec["name"],
        "description": spec["description"],
        "domain": spec["domain"],
        "licenses": ["Apache-2.0"],
        "permitted_uses": ["research", "evaluation", "benchmarking"],
        "sensitivity": "public",
        "required_envassure": ">=0.2.0b1",
        "required_ir": "0.2.0",
        "connector_type": "fixture_oracle",
        "workflow_id": spec["workflow_id"],
        "public_components": [
            "sources/",
            "decisions/",
            "baselines/public-baseline.json",
            "probes/",
            "expected-public/",
        ],
        "hidden_components": [
            "concealed_oracle_episodes",
            f"digest:{spec['hidden_oracle']}",
        ],
        "probe_families": list(spec["probe_families"]),
        "metrics": [
            "transition_agreement",
            "auth_agreement",
            "failure_agreement",
            "observation_agreement",
            "leakage",
            "solvability",
            "diff_match",
        ],
        "limitations": [
            "Hidden oracle episodes are digest-pinned and not shipped as answer keys.",
            "Interface agreement is not production behavioral parity.",
            "Dimension metrics must not be collapsed into a single score.",
        ],
        "maintainers": [
            {"name": "EnvAssure maintainers", "role": "governance"},
        ],
        "governance_owner": "EnvAssure maintainers",
        "digests": {
            "hidden_oracle": spec["hidden_oracle"],
            "baseline_world": baseline_digest,
        },
        "includes": {
            "source_conflict": "sources/conflict.yaml",
            "open_ambiguity": "decisions/open-ambiguity.yaml",
            "hidden_reference": "probes/hidden-reference.yaml",
            "unsupported_uses": "world/unsupported-uses.yaml",
            "baseline": "baselines/public-baseline.json",
            "mutation_suite": "probes/mutation-suite.yaml",
            "differential_plan": "probes/differential-plan.yaml",
        },
        "metadata": {
            "fixture_path": spec["fixture"],
            "mapped_from": "envassure.benchmark.workflows",
        },
    }
    (pack_dir / "pack.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    tree_digest = compute_pack_tree_digest(pack_dir)
    manifest["digests"]["pack_tree"] = tree_digest
    (pack_dir / "pack.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )
    return pack_dir


def main() -> None:
    PACKS.mkdir(parents=True, exist_ok=True)
    for spec in PACKS_SPEC:
        path = _write_pack(spec)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
