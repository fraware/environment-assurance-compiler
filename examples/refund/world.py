"""Refund conflict reference: intentional multi-source ambiguity AMB-0042."""

from __future__ import annotations

from pathlib import Path

from envassure.api import World, provenance
from envassure.facts.store import FactStore
from envassure.ir.models import AmbiguityRecord, WorldDefinition
from envassure.reconciliation import ReconciliationResult, reconcile
from envassure.sources import import_source
from envassure.workspace.config import SourcePrecedenceSection

_SOURCES = Path(__file__).resolve().parent / "sources"


def example_root() -> Path:
    return Path(__file__).resolve().parent


def collect_refund_facts() -> FactStore:
    """Import OpenAPI, SOP, and trace sources into one fact store."""
    store = FactStore()
    store.extend(import_source("openapi", _SOURCES / "api.yaml"))
    store.extend(import_source("procedure", _SOURCES / "refund-sop.md"))
    store.extend(import_source("traces", _SOURCES / "trace-0187.jsonl"))
    return store


def reconcile_refund(
    precedence: SourcePrecedenceSection | None = None,
) -> ReconciliationResult:
    """Reconcile refund sources; expected to surface AMB-0042."""
    store = collect_refund_facts()
    return reconcile(store.list(), precedence or SourcePrecedenceSection())


def find_amb_0042(result: ReconciliationResult) -> AmbiguityRecord:
    for amb in result.ambiguities:
        if amb.id == "AMB-0042":
            return amb
    raise LookupError("AMB-0042 not produced by refund reconciliation")


def build_refund_world() -> WorldDefinition:
    """Partial world builder — operational semantics left open via AMB-0042."""
    result = reconcile_refund()
    amb = find_amb_0042(result)

    world = World(
        environment_id="refund.v1",
        name="Support Refund Workflow",
        description=(
            "Refund workflow with intentional conflicting sources. "
            "Timeout/retry/idempotency remain open until AMB-0042 is decided."
        ),
        domain="support",
    )
    world.definition.task_families = ["refund"]
    world.definition.determinism = "seeded_recorded_externals"
    world.definition.declared_fidelity_level = "EF-0"
    world.definition.known_unsupported_behavior = [
        "retry_after_timeout_without_decision",
        "idempotency_key_unspecified",
    ]
    world.definition.semantic_sources = [
        "sources/api.yaml",
        "sources/refund-sop.md",
        "sources/trace-0187.jsonl",
    ]
    world.definition.ambiguities = [
        amb,
        *[a for a in result.ambiguities if a.id != "AMB-0042"],
    ]

    world.state(
        "refund_status",
        type="enum",
        enum_values=["none", "pending", "committed", "failed"],
        initial_generator="none",
        provenance=provenance(source_ids=["sources/api.yaml"]),
    )
    world.actor(
        "agent",
        actor_class="support_agent",
        available_actions=["submit_refund"],
        observation_projection_id="agent_view",
    )
    world.observation(
        "agent_view",
        target_actor_class="support_agent",
        visible_paths=["refund_status"],
    )
    # Intentionally omit retry_behavior / idempotency — gated by AMB-0042.
    world.action(
        "submit_refund",
        actor_classes=["support_agent"],
        writes=["refund_status"],
        intended_effects=["refund_status = committed"],
        success_outcomes=["accepted"],
        failure_ids=[],
        timeout_behavior="http_504_no_state_semantics",
        retry_behavior=None,
        idempotency=None,
        unsupported_semantics=[
            "retry_behavior",
            "idempotency",
            "authoritative_state_on_504",
        ],
        provenance=provenance(
            source_ids=[
                "sources/api.yaml",
                "sources/refund-sop.md",
                "sources/trace-0187.jsonl",
            ],
        ),
    )
    world.transition(
        "t_submit_refund",
        action_id="submit_refund",
        events=["refund.submitted"],
        unsupported_assumptions=["timeout_may_have_committed"],
    )
    return world.compile()
