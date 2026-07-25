"""Stochastic inventory / scheduling minimal WorldDefinition."""

from __future__ import annotations

from envassure.api import World, constraint, provenance
from envassure.ir.models import TransitionBranch, WorldDefinition


def build_inventory_world() -> WorldDefinition:
    """
    Minimal stochastic inventory/scheduling environment.

    Stock depletes on fulfill with a stochastic stockout branch; replenish is
    authorized for planners. Demonstrates statistical determinism class.
    """
    world = World(
        environment_id="inventory.scheduling.v1",
        name="Stochastic Inventory Scheduling",
        description="Minimal inventory with stochastic fulfill / stockout transitions.",
        domain="operations",
    )
    world.definition.task_families = ["fulfillment", "replenishment"]
    world.definition.determinism = "statistical"
    world.definition.stochasticity_model = "categorical_branches"
    world.definition.declared_fidelity_level = "EF-1"
    world.definition.termination_semantics = "goal_or_horizon"
    world.definition.reset_semantics = "full_reset"

    world.state(
        "on_hand",
        type="resource_counter",
        initial_generator="10",
        mutation_authority=["fulfill", "replenish"],
        provenance=provenance(source_ids=["manual"]),
    )
    world.state(
        "backlog",
        type="resource_counter",
        initial_generator="0",
        mutation_authority=["fulfill", "arrive_demand"],
    )
    world.state(
        "day",
        type="scalar",
        initial_generator="0",
        mutation_authority=["tick"],
    )
    # Hidden service-level oracle — must not appear in policy observations.
    world.state(
        "true_fill_rate",
        type="scalar",
        initial_generator="1.0",
        evaluator_visible=True,
        policy_visible=False,
        mutation_authority=["fulfill"],
    )

    world.actor(
        "planner",
        actor_class="planner",
        roles=["planner"],
        authority_source="role:planner",
        available_actions=["replenish", "observe", "tick"],
        observation_projection_id="planner_view",
    )
    world.actor(
        "operator",
        actor_class="operator",
        roles=["operator"],
        available_actions=["arrive_demand", "fulfill", "observe"],
        observation_projection_id="operator_view",
    )

    world.observation(
        "planner_view",
        target_actor_class="planner",
        visible_paths=["on_hand", "backlog", "day"],
        omitted_paths=["true_fill_rate"],
    )
    world.observation(
        "operator_view",
        target_actor_class="operator",
        visible_paths=["on_hand", "backlog"],
        omitted_paths=["true_fill_rate"],
    )

    world.failure(
        "stockout",
        category="resource_exhaustion",
        description="Insufficient on_hand to fulfill demand",
        retryable=True,
        transaction_effect="abort",
    )
    world.failure(
        "unauthorized_replenish",
        category="authorization",
        description="Caller lacks planner role",
        retryable=False,
    )

    world.action(
        "arrive_demand",
        actor_classes=["operator"],
        writes=["backlog"],
        intended_effects=["backlog += demand"],
        resource_effects=["backlog += demand"],
        success_outcomes=["ok"],
        provenance=provenance(source_ids=["manual"]),
    )
    world.action(
        "fulfill",
        actor_classes=["operator"],
        reads=["on_hand", "backlog"],
        writes=["on_hand", "backlog", "true_fill_rate"],
        intended_effects=["on_hand -= shipped; backlog -= shipped"],
        resource_effects=["on_hand conserved_unless_ship; backlog reduced"],
        failure_ids=["stockout"],
        success_outcomes=["shipped", "partial"],
        retry_behavior="retry_once",
        idempotency="client_token",
        timeout_behavior="fail_closed",
        transaction_boundary="fulfill_tx",
    )
    world.action(
        "replenish",
        actor_classes=["planner"],
        authorization="role:planner",
        writes=["on_hand"],
        intended_effects=["on_hand += qty"],
        resource_effects=["on_hand += qty"],
        failure_ids=["unauthorized_replenish"],
        success_outcomes=["ok"],
    )
    world.action(
        "tick",
        actor_classes=["planner"],
        writes=["day"],
        intended_effects=["day += 1"],
        success_outcomes=["ok"],
    )
    world.action(
        "observe",
        actor_classes=["planner", "operator"],
        reads=["on_hand", "backlog"],
        success_outcomes=["ok"],
    )

    world.transition(
        "t_arrive",
        action_id="arrive_demand",
        events=["demand.arrived"],
    )
    world.transition(
        "t_fulfill",
        action_id="fulfill",
        kind="stochastic",
        branches=[
            TransitionBranch(
                id="t_fulfill.ship",
                probability=0.8,
                probability_source="historical_fill",
                events=["order.shipped"],
            ),
            TransitionBranch(
                id="t_fulfill.stockout",
                probability=0.2,
                probability_source="historical_fill",
                events=["order.stockout"],
                terminal=False,
            ),
        ],
    )
    world.transition("t_replenish", action_id="replenish", events=["stock.replenished"])
    world.transition("t_tick", action_id="tick", events=["clock.tick"])
    world.transition("t_observe", action_id="observe", events=["state.observed"])

    world.verifier(
        "v_non_negative_stock",
        statement="on_hand is always >= 0",
        decision_rule="state.on_hand >= 0",
        status="tested",
    )
    world.verifier(
        "v_planner_only_replenish",
        statement="replenish requires planner role",
        decision_rule="actor.roles contains planner",
        mechanism="authority",
        status="tested",
    )

    world.task(
        "clear_backlog",
        family="fulfillment",
        intent="Reduce backlog to zero within horizon via fulfill and replenish",
        goal_claims=["backlog == 0"],
        verifier_claim_ids=["v_non_negative_stock", "v_planner_only_replenish"],
        initial_constraints=[constraint("on_hand >= 0")],
        actor_assignment={"planner": "planner", "operator": "operator"},
        permitted_tools=["fulfill", "replenish", "arrive_demand", "tick"],
        horizon=20,
        solvability_method="bounded_bfs",
    )
    return world.compile()
