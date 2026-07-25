"""Deterministic counter service reference pack (manual SDK)."""

from __future__ import annotations

from envassure.api import World, constraint, provenance
from envassure.ir.models import WorldDefinition


def build_counter_world() -> WorldDefinition:
    world = World(
        environment_id="counter.v1",
        name="Deterministic Counter",
        description="Minimal fully-deterministic counter service.",
        domain="reference",
    )
    world.definition.task_families = ["increment"]
    world.definition.determinism = "fully_deterministic"
    world.definition.declared_fidelity_level = "EF-1"

    world.state(
        "count",
        type="resource_counter",
        initial_generator="0",
        provenance=provenance(source_ids=["manual"]),
    )
    world.actor(
        "client",
        actor_class="client",
        available_actions=["increment", "reset", "get"],
        observation_projection_id="client_view",
    )
    world.actor(
        "admin",
        actor_class="admin",
        roles=["admin"],
        authority_source="role:admin",
        available_actions=["reset", "get", "increment"],
        observation_projection_id="client_view",
    )
    world.observation(
        "client_view",
        target_actor_class="client",
        visible_paths=["count"],
    )
    world.action(
        "increment",
        actor_classes=["client", "admin"],
        writes=["count"],
        intended_effects=["count += 1"],
        resource_effects=["count += 1"],
        success_outcomes=["ok"],
        idempotency="none",
        provenance=provenance(source_ids=["manual"]),
    )
    world.action(
        "reset",
        actor_classes=["client", "admin"],
        writes=["count"],
        intended_effects=["count = 0"],
        resource_effects=["count = 0"],
        success_outcomes=["ok"],
        authorization="role:admin",
    )
    world.action(
        "get",
        actor_classes=["client", "admin"],
        reads=["count"],
        success_outcomes=["ok"],
    )
    world.transition(
        "t_increment",
        action_id="increment",
        events=["count.incremented"],
    )
    world.transition("t_reset", action_id="reset", events=["count.reset"])
    world.transition("t_get", action_id="get", events=["count.read"])
    world.verifier(
        "v_non_negative",
        statement="count is always >= 0",
        decision_rule="state.count >= 0",
        status="tested",
    )
    world.task(
        "reach_three",
        family="increment",
        intent="Reach count == 3 via increments",
        goal_claims=["count == 3"],
        verifier_claim_ids=["v_non_negative"],
        initial_constraints=[constraint("count == 0")],
        horizon=10,
    )
    return world.compile()
