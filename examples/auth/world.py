"""Multi-actor authorization workflow reference pack."""

from __future__ import annotations

from envassure.api import World, provenance
from envassure.ir.models import WorldDefinition


def build_auth_world() -> WorldDefinition:
    world = World(
        environment_id="auth.workflow.v1",
        name="Authorization Workflow",
        description="Requester and approver with permissioned approve action.",
        domain="reference",
    )
    world.definition.task_families = ["approval"]
    world.definition.concurrency_model = "multi_actor"
    world.definition.determinism = "fully_deterministic"

    world.state(
        "request_status",
        type="enum",
        enum_values=["draft", "pending", "approved", "denied"],
        initial_generator="draft",
    )
    world.state("requester_id", type="scalar")
    world.state("approver_id", type="scalar", evaluator_visible=True, policy_visible=False)

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
        omitted_paths=["approver_id"],
    )
    world.observation(
        "approver_view",
        target_actor_class="approver",
        visible_paths=["request_status", "requester_id"],
        omitted_paths=["approver_id"],
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
        # String enum values must be quoted; bare names resolve as state paths (None).
        intended_effects=['request_status = "pending"'],
        success_outcomes=["ok"],
        provenance=provenance(source_ids=["manual"]),
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
    world.verifier(
        "v_only_approver",
        statement="approve requires approver role",
        decision_rule="actor.roles contains approver",
        mechanism="authority",
        status="tested",
    )
    world.task(
        "get_approval",
        family="approval",
        intent="Submit and obtain approval",
        goal_claims=["request_status == approved"],
        verifier_claim_ids=["v_only_approver"],
        actor_assignment={"user": "requester", "reviewer": "approver"},
        horizon=5,
    )
    return world.compile()
