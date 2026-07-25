"""Semantic-category mutation of WorldDefinition for testing."""

from __future__ import annotations

from enum import StrEnum

from envassure.analysis.static import MutationScope, list_mutation_scopes
from envassure.ir.models import WorldDefinition


class MutationCategory(StrEnum):
    """Semantic mutation categories used by metamorphic / mutation testing."""

    PERMISSION = "permission"
    TIMEOUT = "timeout"
    OBSERVATION_LEAK = "observation_leak"
    RESET_INTEGRITY = "reset_integrity"
    MUTATION_SCOPE = "mutation_scope"
    AUTHORITY = "authority"
    TRANSACTION_RETRY = "transaction_retry"
    TERMINATION = "termination"
    INFORMATION_FLOW = "information_flow"


def apply_mutation(
    world: WorldDefinition,
    category: MutationCategory | str,
    *,
    seed: int = 0,
    target_id: str | None = None,
) -> WorldDefinition:
    """
    Return a deep copy of *world* mutated by *category*.

    Mutations are deterministic given (category, seed, target_id).
    """
    cat = MutationCategory(category)
    mutant = world.model_copy(deep=True)
    if cat is MutationCategory.PERMISSION:
        return _mutate_permission(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.TIMEOUT:
        return _mutate_timeout(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.OBSERVATION_LEAK:
        return _mutate_observation_leak(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.RESET_INTEGRITY:
        return _mutate_reset_integrity(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.MUTATION_SCOPE:
        return _mutate_mutation_scope(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.AUTHORITY:
        return _mutate_authority(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.TRANSACTION_RETRY:
        return _mutate_transaction_retry(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.TERMINATION:
        return _mutate_termination(mutant, seed=seed, target_id=target_id)
    if cat is MutationCategory.INFORMATION_FLOW:
        return _mutate_information_flow(mutant, seed=seed, target_id=target_id)
    raise ValueError(f"unsupported mutation category: {category!r}")


def mutation_targets(world: WorldDefinition, category: MutationCategory | str) -> list[str]:
    """List element ids that can be mutated for *category*."""
    cat = MutationCategory(category)
    if cat is MutationCategory.PERMISSION:
        return [a.id for a in world.actions]
    if cat is MutationCategory.TIMEOUT:
        return [a.id for a in world.actions]
    if cat is MutationCategory.OBSERVATION_LEAK:
        return [s.id for s in world.state if not s.evaluator_visible]
    if cat is MutationCategory.RESET_INTEGRITY:
        return [s.id for s in world.state]
    if cat is MutationCategory.MUTATION_SCOPE:
        return [s.id for s in world.state if s.mutation_authority]
    if cat is MutationCategory.AUTHORITY:
        return [a.id for a in world.actions if a.authorization]
    if cat is MutationCategory.TRANSACTION_RETRY:
        return [a.id for a in world.actions]
    if cat is MutationCategory.TERMINATION:
        return [t.id for t in world.tasks] or [world.environment_id]
    if cat is MutationCategory.INFORMATION_FLOW:
        return [o.id for o in world.observations]
    return []


def _pick(ids: list[str], *, seed: int, target_id: str | None) -> str | None:
    if target_id is not None:
        return target_id if target_id in ids else None
    if not ids:
        return None
    return ids[seed % len(ids)]


def _mutate_permission(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    action_id = _pick([a.id for a in world.actions], seed=seed, target_id=target_id)
    if action_id is None:
        return world
    for action in world.actions:
        if action.id == action_id:
            if action.authorization:
                action.authorization = None
            else:
                action.authorization = "role:mutated_deny"
            break
    return world


def _mutate_timeout(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    action_id = _pick([a.id for a in world.actions], seed=seed, target_id=target_id)
    if action_id is None:
        return world
    for action in world.actions:
        if action.id == action_id:
            action.timeout_behavior = "fail_closed"
            action.retry_behavior = None  # intentional defect: EAC4027
            break
    return world


def _mutate_observation_leak(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    """Inject evaluator_visible state into a policy observation."""
    candidates = [s for s in world.state if not s.evaluator_visible]
    if target_id is not None:
        candidates = [s for s in candidates if s.id == target_id] or [
            s for s in world.state if s.id == target_id
        ]
    if not candidates or not world.observations:
        if world.state and world.observations:
            var = world.state[seed % len(world.state)]
            var.evaluator_visible = True
            var.policy_visible = False
            obs = world.observations[seed % len(world.observations)]
            if var.id not in obs.visible_paths:
                obs.visible_paths.append(var.id)
        return world

    var = candidates[seed % len(candidates)]
    var.evaluator_visible = True
    var.policy_visible = False
    obs = world.observations[seed % len(world.observations)]
    if var.id not in obs.visible_paths:
        obs.visible_paths.append(var.id)
    if var.id in obs.omitted_paths:
        obs.omitted_paths = [p for p in obs.omitted_paths if p != var.id]
    return world


def _mutate_reset_integrity(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    state_id = _pick([s.id for s in world.state], seed=seed, target_id=target_id)
    if state_id is None:
        return world
    world.reset_semantics = "full_reset"
    for var in world.state:
        if var.id == state_id:
            var.reset_class = "external"
            break
    return world


def _mutate_mutation_scope(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    """Force an unauthorized write against a declared mutation_authority list."""
    guarded = [s for s in world.state if s.mutation_authority]
    state_id = _pick([s.id for s in guarded], seed=seed, target_id=target_id)
    if state_id is None or not world.actions:
        return world
    var = next(s for s in world.state if s.id == state_id)
    var.mutation_authority = ["__no_such_writer__"]
    action = world.actions[seed % len(world.actions)]
    if state_id not in action.writes and state_id not in [
        w.split(".", 1)[0] for w in action.writes
    ]:
        action.writes = [*action.writes, state_id]
    return world


def _mutate_authority(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    action_id = _pick(
        [a.id for a in world.actions if a.authorization],
        seed=seed,
        target_id=target_id,
    )
    if action_id is None:
        # Invent authorization with no discharging actor.
        if world.actions:
            world.actions[seed % len(world.actions)].authorization = "role:mutated_orphan"
        return world
    for action in world.actions:
        if action.id == action_id:
            action.authorization = "role:mutated_orphan_auth"
            break
    for actor in world.actors:
        if actor.authority_source and "mutated_orphan" in actor.authority_source:
            actor.authority_source = None
        actor.roles = [r for r in actor.roles if "mutated_orphan" not in r]
        actor.capabilities = [c for c in actor.capabilities if "mutated_orphan" not in c]
        actor.delegation_rules = [d for d in actor.delegation_rules if "mutated_orphan" not in d]
    return world


def _mutate_transaction_retry(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    action_id = _pick([a.id for a in world.actions], seed=seed, target_id=target_id)
    if action_id is None:
        return world
    for action in world.actions:
        if action.id == action_id:
            action.retry_behavior = "retry_once"
            action.idempotency = None
            action.compensation_action = action.compensation_action or "compensate_missing"
            action.transaction_boundary = None
            break
    return world


def _mutate_termination(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    _ = seed
    _ = target_id
    world.termination_semantics = "goal"
    for transition in world.transitions:
        for branch in transition.branches:
            branch.terminal = False
    if world.tasks:
        world.tasks[0].horizon = 5
    return world


def _mutate_information_flow(
    world: WorldDefinition,
    *,
    seed: int,
    target_id: str | None,
) -> WorldDefinition:
    obs_id = _pick([o.id for o in world.observations], seed=seed, target_id=target_id)
    if obs_id is None:
        return world
    for obs in world.observations:
        if obs.id == obs_id:
            if obs.visible_paths:
                path = obs.visible_paths[0]
                if path not in obs.omitted_paths:
                    obs.omitted_paths.append(path)
                obs.information_flow_labels = [f"{path.split('.', 1)[0]}:deny"]
            break
    return world


__all__ = [
    "MutationCategory",
    "MutationScope",
    "apply_mutation",
    "list_mutation_scopes",
    "mutation_targets",
]
