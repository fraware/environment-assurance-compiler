"""OPA authorization example (E4).

Demonstrates ``eac obligations generate|report`` against a small auth world.
Requires system OPA for ``eac obligations test`` / ``evaluate`` (not vendored).
"""

from __future__ import annotations

import json
from pathlib import Path

from envassure.api import World, provenance
from envassure.ir.models import WorldDefinition


def build_opa_auth_world() -> WorldDefinition:
    world = World(
        environment_id="opa.authorization.v1",
        name="OPA Authorization Example",
        description="Minimal authorization + idempotency world for OPA obligation demos.",
        domain="reference",
    )
    world.definition.task_families = ["approve"]
    world.definition.determinism = "fully_deterministic"
    world.definition.declared_fidelity_level = "EF-1"

    world.state(
        "request_status",
        type="enum",
        enum_values=["draft", "pending", "approved", "denied"],
        initial_generator='"draft"',
        provenance=provenance(source_ids=["manual"]),
    )
    world.actor(
        "requester",
        actor_class="requester",
        available_actions=["submit", "observe"],
        observation_projection_id="requester_view",
    )
    world.actor(
        "approver",
        actor_class="approver",
        roles=["approver"],
        authority_source="role:approver",
        available_actions=["approve", "deny", "observe"],
        observation_projection_id="approver_view",
    )
    world.observation(
        "requester_view",
        target_actor_class="requester",
        visible_paths=["request_status"],
    )
    world.observation(
        "approver_view",
        target_actor_class="approver",
        visible_paths=["request_status"],
    )
    world.action(
        "submit",
        actor_classes=["requester"],
        writes=["request_status"],
        intended_effects=['request_status = "pending"'],
        success_outcomes=["ok"],
        idempotency="keyed",
    )
    world.action(
        "approve",
        actor_classes=["approver"],
        writes=["request_status"],
        intended_effects=['request_status = "approved"'],
        authorization="role:approver",
        success_outcomes=["ok"],
        failure_ids=["unauthorized"],
    )
    world.action(
        "deny",
        actor_classes=["approver"],
        writes=["request_status"],
        intended_effects=['request_status = "denied"'],
        authorization="role:approver",
        success_outcomes=["ok"],
        failure_ids=["unauthorized"],
    )
    world.action("observe", actor_classes=["requester", "approver"], success_outcomes=["ok"])
    world.transition("t_submit", action_id="submit", events=["submitted"])
    world.transition("t_approve", action_id="approve", events=["approved"])
    world.transition("t_deny", action_id="deny", events=["denied"])
    world.transition("t_observe", action_id="observe", events=["observed"])
    world.task(
        "get_approval",
        family="approve",
        intent="Reach approved status",
        goal_claims=['request_status == "approved"'],
        horizon=8,
    )
    return world.compile()


def main() -> None:
    root = Path(__file__).resolve().parent
    world = build_opa_auth_world()
    out = root / "input" / "world.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(world.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
