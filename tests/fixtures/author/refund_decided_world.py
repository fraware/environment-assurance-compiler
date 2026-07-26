"""Decided refund world for external-author workflow tests.

Copy this file to a workspace as ``world.py`` after ``eac decide`` has accepted
the classic submit_refund retry conflict. The builder reads workspace
``facts/ambiguities.json`` and ``decisions/``.
"""

from __future__ import annotations

from pathlib import Path

from envassure.api import World, provenance
from envassure.ir.primitives import ProvenanceRef
from envassure.reconciliation import ambiguity_id
from envassure.review import load_ambiguities, load_decisions_dir

CLASSIC_REFUND_RETRY_AMBIGUITY_ID = ambiguity_id(
    "action:submit_refund",
    "retry_behavior",
    "conflict",
)


def build_refund_world():
    """Compile refund IR after expert decision closes retry/idempotency."""
    root = Path(__file__).resolve().parent
    ambiguities = load_ambiguities(root / "facts" / "ambiguities.json")
    decided = next(
        (a for a in ambiguities if a.id == CLASSIC_REFUND_RETRY_AMBIGUITY_ID),
        None,
    )
    if decided is None or decided.status != "accepted":
        raise RuntimeError("expected accepted classic refund retry ambiguity; run eac decide first")

    decisions = {d.decision_id: d for d in load_decisions_dir(root / "decisions")}
    decision = decisions.get(decided.decision_id or "")
    interpretation = (
        decision.chosen_interpretation
        if decision is not None
        else "timeout_then_retry_requires_idempotency_key"
    )
    decided = decided.model_copy(
        update={
            "provenance": ProvenanceRef(
                origin_kind="human_decision",
                notes="projected from eac decide",
                decision_ids=[decided.decision_id] if decided.decision_id else [],
            ),
        }
    )

    world = World(
        environment_id="refund.v1",
        name="Support Refund Workflow",
        description=(
            "Refund workflow after expert decision on retry/idempotency. "
            f"Decision closes {CLASSIC_REFUND_RETRY_AMBIGUITY_ID}."
        ),
        domain="support",
    )
    world.definition.task_families = ["refund"]
    world.definition.determinism = "seeded_recorded_externals"
    world.definition.declared_fidelity_level = "EF-0"
    world.definition.known_unsupported_behavior = ["live_payment_rail"]
    world.definition.semantic_sources = [
        "sources/api.yaml",
        "sources/refund-sop.md",
        "sources/trace-0187.jsonl",
    ]
    world.definition.ambiguities = [decided] + [
        a for a in ambiguities if a.id != CLASSIC_REFUND_RETRY_AMBIGUITY_ID
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
    world.action(
        "submit_refund",
        actor_classes=["support_agent"],
        writes=["refund_status"],
        intended_effects=['refund_status = "committed"'],
        success_outcomes=["accepted"],
        failure_ids=[],
        timeout_behavior="http_504_no_state_semantics",
        retry_behavior=interpretation,
        idempotency="idempotency_key_required",
        provenance=provenance(
            source_ids=[
                "sources/api.yaml",
                "sources/refund-sop.md",
                "sources/trace-0187.jsonl",
            ],
            origin_kind="human_decision",
            decision_ids=[decided.decision_id] if decided.decision_id else [],
            notes="retry/idempotency projected from expert decision",
        ),
    )
    world.transition(
        "t_submit_refund",
        action_id="submit_refund",
        events=["refund.submitted"],
    )
    return world.compile()
