"""Evidence-scoped E1 refund world template for the public example.

This module is copied into an initialized workspace after source reconciliation.
It deliberately refuses to project unresolved retry policy or incomplete
 timeout/idempotency semantics. The resulting environment is executable only for
 the modeled non-timeout path; the classic retry conflict remains explicit.
"""

from __future__ import annotations

from pathlib import Path

from envassure.api import World, provenance
from envassure.reconciliation import ambiguity_id
from envassure.review import load_ambiguities

CLASSIC_REFUND_RETRY_AMBIGUITY_ID = ambiguity_id(
    "action:submit_refund",
    "retry_behavior",
    "conflict",
)


def build_refund_world():
    """Compile only the supported, non-timeout subset of refund semantics."""
    root = Path(__file__).resolve().parent
    ambiguities = load_ambiguities(root / "facts" / "ambiguities.json")
    classic = next(
        (a for a in ambiguities if a.id == CLASSIC_REFUND_RETRY_AMBIGUITY_ID),
        None,
    )
    if classic is None or classic.status != "open":
        raise RuntimeError(
            "expected the classic refund retry conflict to remain open; "
            "this scoped template must not silently resolve it"
        )

    action_conflicts = [
        a
        for a in ambiguities
        if a.subject == "action:submit_refund" and a.conflict_class == "semantic_conflict"
    ]
    if [a.id for a in action_conflicts] != [CLASSIC_REFUND_RETRY_AMBIGUITY_ID]:
        raise RuntimeError(
            "expected exactly the classic retry-policy semantic conflict; "
            f"got {[a.id for a in action_conflicts]}"
        )

    world = World(
        environment_id="refund.v1",
        name="Support Refund Workflow",
        description=(
            "OpenAPI-backed refund workflow scoped to the supported non-timeout path. "
            "Retry policy remains conflicted; timeout authoritative-state and "
            "idempotency semantics remain incomplete and are excluded from execution."
        ),
        domain="support",
    )
    world.definition.task_families = ["refund"]
    world.definition.determinism = "seeded_recorded_externals"
    world.definition.declared_fidelity_level = "EF-0"
    world.definition.known_unsupported_behavior = [
        "live_payment_rail",
        "timeout_retry_idempotency_semantics",
    ]
    world.definition.semantic_sources = [
        "sources/api.yaml",
        "sources/refund-sop.md",
        "sources/trace-0187.jsonl",
    ]
    world.definition.ambiguities = ambiguities

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
    world.action(
        "submit_refund",
        actor_classes=["support_agent"],
        writes=["refund_status"],
        intended_effects=['refund_status = "committed"'],
        success_outcomes=["accepted"],
        failure_ids=[],
        unsupported_semantics=[
            "timeout_behavior",
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
            origin_kind="inferred",
            notes=(
                "non-timeout executable projection only; retry policy is conflicted "
                "and timeout/idempotency evidence is insufficient for execution"
            ),
        ),
    )
    world.transition(
        "t_submit_refund",
        action_id="submit_refund",
        events=["refund.submitted"],
    )
    return world.compile()
