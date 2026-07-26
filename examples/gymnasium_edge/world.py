"""Gymnasium edge example (E5) — payload-bearing Dict action space + check_env.

Evolves the counter pattern with a bounded integer payload action so the
release-qualified Gymnasium adapter exercises ``spaces.Dict`` actions.
"""

from __future__ import annotations

import json
from pathlib import Path

from envassure.api import World, provenance
from envassure.ir.models import WorldDefinition


def build_gymnasium_edge_world() -> WorldDefinition:
    world = World(
        environment_id="gymnasium.edge.v1",
        name="Gymnasium Edge Payload Counter",
        description="Payload-bearing set action for Gymnasium Dict action-space demos.",
        domain="reference",
    )
    world.definition.task_families = ["set_value"]
    world.definition.determinism = "fully_deterministic"
    world.definition.declared_fidelity_level = "EF-1"

    world.state(
        "n",
        type="resource_counter",
        initial_generator="0",
        provenance=provenance(source_ids=["manual"]),
    )
    world.actor(
        "agent",
        actor_class="agent",
        available_actions=["set", "get"],
        observation_projection_id="agent_view",
    )
    world.observation(
        "agent_view",
        target_actor_class="agent",
        visible_paths=["n"],
    )
    world.action(
        "set",
        actor_classes=["agent"],
        writes=["n"],
        intended_effects=["n = payload.value"],
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer", "minimum": 0, "maximum": 5}},
            "additionalProperties": False,
        },
        success_outcomes=["ok"],
        provenance=provenance(source_ids=["manual"]),
    )
    world.action(
        "get",
        actor_classes=["agent"],
        reads=["n"],
        success_outcomes=["ok"],
    )
    world.transition("t_set", action_id="set", events=["n.set"])
    world.transition("t_get", action_id="get", events=["n.read"])
    world.task(
        "reach_three",
        family="set_value",
        intent="Reach n == 3 via payload set",
        goal_claims=["n == 3"],
        horizon=8,
    )
    return world.compile()


def main() -> None:
    root = Path(__file__).resolve().parent
    world = build_gymnasium_edge_world()
    out = root / "input" / "world.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(world.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
