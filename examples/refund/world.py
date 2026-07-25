"""Refund conflict reference: intentional multi-source ambiguity (hashed id).

Historical demo id ``AMB-0042`` is retained as a *fixture alias* for the stable
hashed ambiguity id produced by reconciliation v2. Production reconcile never
hard-codes ``AMB-0042``.
"""

from __future__ import annotations

from pathlib import Path

from envassure.api import World, provenance
from envassure.facts.store import FactStore
from envassure.ir.models import AmbiguityRecord, WorldDefinition
from envassure.reconciliation import ReconciliationResult, ambiguity_id, reconcile
from envassure.sources import import_source
from envassure.workspace.config import SourcePrecedenceSection

_SOURCES = Path(__file__).resolve().parent / "sources"

# Stable hashed id for classic submit_refund retry_behavior conflict.
CLASSIC_REFUND_RETRY_AMBIGUITY_ID = ambiguity_id(
    "action:submit_refund",
    "retry_behavior",
    "conflict",
)
# Historical packaged-demo alias — maps to CLASSIC_REFUND_RETRY_AMBIGUITY_ID.
AMB_0042_ALIAS = "AMB-0042"
FIXTURE_AMBIGUITY_ALIASES: dict[str, str] = {
    AMB_0042_ALIAS: CLASSIC_REFUND_RETRY_AMBIGUITY_ID,
}


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
    """Reconcile refund sources; surfaces hashed classic retry conflict."""
    store = collect_refund_facts()
    return reconcile(store.list(), precedence or SourcePrecedenceSection())


def resolve_fixture_ambiguity_id(ambiguity_id_or_alias: str) -> str:
    """Map historical demo aliases (e.g. AMB-0042) to stable hashed ids."""
    return FIXTURE_AMBIGUITY_ALIASES.get(ambiguity_id_or_alias, ambiguity_id_or_alias)


def find_amb_0042(result: ReconciliationResult) -> AmbiguityRecord:
    """Locate the classic refund retry conflict (hashed id; AMB-0042 alias)."""
    target = CLASSIC_REFUND_RETRY_AMBIGUITY_ID
    for amb in result.ambiguities:
        if amb.id == target:
            return amb
    raise LookupError(
        f"{AMB_0042_ALIAS} alias target {target} not produced by refund reconciliation"
    )


def with_demo_alias(ambiguity: AmbiguityRecord) -> AmbiguityRecord:
    """Return a copy tagged with the historical AMB-0042 id for demo docs only."""
    if ambiguity.id != CLASSIC_REFUND_RETRY_AMBIGUITY_ID:
        return ambiguity
    return ambiguity.model_copy(update={"id": AMB_0042_ALIAS})


def build_refund_world() -> WorldDefinition:
    """Partial world builder — operational semantics left open via classic conflict."""
    result = reconcile_refund()
    amb = find_amb_0042(result)
    # Demo surface keeps AMB-0042 label; authoritative reconcile id stays hashed.
    demo_amb = with_demo_alias(amb)

    world = World(
        environment_id="refund.v1",
        name="Support Refund Workflow",
        description=(
            "Refund workflow with intentional conflicting sources. "
            f"Timeout/retry/idempotency remain open until {AMB_0042_ALIAS} "
            f"(hashed {CLASSIC_REFUND_RETRY_AMBIGUITY_ID}) is decided."
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
        demo_amb,
        *[a for a in result.ambiguities if a.id != CLASSIC_REFUND_RETRY_AMBIGUITY_ID],
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
    # Intentionally omit retry_behavior / idempotency — gated by classic conflict.
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
