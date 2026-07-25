"""Static assurance analyses over WorldDefinition (bounded, IR-only)."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic, DiagnosticReport
from envassure.ir.models import (
    ActionContract,
    ActorDefinition,
    TaskTemplate,
    WorldDefinition,
)
from envassure.runtime.authorization import (
    actor_discharges as _actor_discharges,
    delegation_targets as _delegation_targets,
    normalize_auth_token as _normalize_auth_token,
)


@dataclass(slots=True)
class ReachabilityResult:
    """Bounded BFS reachability over the action graph."""

    reachable_actions: set[str]
    depths: dict[str, int]
    bound: int
    truncated: bool = False


@dataclass(slots=True)
class MutationScope:
    """State variables writable by an action (mutation authority surface)."""

    action_id: str
    writes: list[str]
    mutation_authority: list[str]


@dataclass(slots=True)
class StaticAnalysisResult:
    """Aggregate static analysis output."""

    report: DiagnosticReport
    reachability: ReachabilityResult
    mutation_scopes: list[MutationScope] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def diagnostics(self) -> list[Diagnostic]:
        return list(self.report.diagnostics)


def analyze_world(
    world: WorldDefinition,
    *,
    bfs_bound: int = 64,
) -> StaticAnalysisResult:
    """Run Phase-4 static analyses and return diagnostics + structured results."""
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    reachability = _bounded_reachability(world, bound=bfs_bound)
    scopes = list_mutation_scopes(world)

    _check_reference_integrity(world, report)
    _check_precondition_guards(world, report)
    _check_mutation_scopes(world, report)
    _check_unreachable_actions(world, reachability, report)
    _check_solvability(world, reachability, report)
    _check_reset_integrity(world, report)
    _check_authority_delegation(world, report)
    _check_information_flow(world, report)
    _check_resource_conservation(world, report)
    _check_transaction_retry(world, report)
    _check_termination_integrity(world, report)

    return StaticAnalysisResult(
        report=report,
        reachability=reachability,
        mutation_scopes=scopes,
        details={
            "reachable_action_count": len(reachability.reachable_actions),
            "action_count": len(world.actions),
            "bfs_bound": bfs_bound,
            "checks": [
                "reference_integrity",
                "precondition_guards",
                "mutation_scope",
                "unreachable_actions",
                "solvability",
                "reset_integrity",
                "authority",
                "information_flow",
                "resource_conservation",
                "transaction_retry",
                "termination_integrity",
            ],
        },
    )


def list_mutation_scopes(world: WorldDefinition) -> list[MutationScope]:
    """List mutation scopes (writable state) per action."""
    state_index = world.index_state()
    scopes: list[MutationScope] = []
    for action in world.actions:
        authorities: list[str] = []
        for path in action.writes:
            root = path.split(".", 1)[0]
            var = state_index.get(root)
            if var is not None:
                authorities.extend(var.mutation_authority)
        scopes.append(
            MutationScope(
                action_id=action.id,
                writes=list(action.writes),
                mutation_authority=sorted(set(authorities)),
            )
        )
    return scopes


def _action_successors(world: WorldDefinition) -> dict[str, set[str]]:
    """
    Build an action-successor graph from:

    1. Actor ``available_actions`` cliques (same actor can sequence those actions)
    2. Shared ``actor_classes`` when availability is undeclared
    3. Dataflow edges: writer of state S enables readers/writers of S (enabling)
    4. Explicit transition compensation / recovery links
    """
    action_ids = {a.id for a in world.actions}
    class_actions: dict[str, set[str]] = {}
    writers: dict[str, set[str]] = {}
    readers: dict[str, set[str]] = {}
    for action in world.actions:
        for cls in action.actor_classes:
            class_actions.setdefault(cls, set()).add(action.id)
        for path in action.writes:
            writers.setdefault(path.split(".", 1)[0], set()).add(action.id)
        for path in action.reads:
            readers.setdefault(path.split(".", 1)[0], set()).add(action.id)

    successors: dict[str, set[str]] = {a.id: set() for a in world.actions}
    for actor in world.actors:
        available = [aid for aid in actor.available_actions if aid in action_ids]
        for aid in available:
            successors[aid].update(available)

    for action in world.actions:
        if not successors[action.id]:
            for cls in action.actor_classes:
                successors[action.id] |= class_actions.get(cls, set())
            for other in world.actions:
                if other.id == action.id:
                    continue
                if set(action.actor_classes) & set(other.actor_classes):
                    successors[action.id].add(other.id)

        # Dataflow enabling: after writing S, any action that reads/writes S can follow
        # when they share an actor class or either side is globally available.
        written = {path.split(".", 1)[0] for path in action.writes}
        for state_id in written:
            for nxt in writers.get(state_id, set()) | readers.get(state_id, set()):
                if nxt == action.id:
                    continue
                nxt_action = next(a for a in world.actions if a.id == nxt)
                share = set(action.actor_classes) & set(nxt_action.actor_classes)
                if share or not action.actor_classes or not nxt_action.actor_classes:
                    successors[action.id].add(nxt)

        if action.compensation_action and action.compensation_action in action_ids:
            successors[action.id].add(action.compensation_action)

    return successors


def _seed_actions(world: WorldDefinition) -> set[str]:
    seeds: set[str] = set()
    for actor in world.actors:
        seeds.update(actor.available_actions)
    if not seeds:
        seeds = {a.id for a in world.actions}
    return seeds & {a.id for a in world.actions}


def _bounded_reachability(world: WorldDefinition, *, bound: int) -> ReachabilityResult:
    successors = _action_successors(world)
    seeds = _seed_actions(world)
    depths: dict[str, int] = {}
    queue: deque[str] = deque()
    for seed in sorted(seeds):
        depths[seed] = 0
        queue.append(seed)

    truncated = False
    visited_expansions = 0
    while queue:
        current = queue.popleft()
        depth = depths[current]
        if depth >= bound:
            truncated = True
            continue
        for nxt in sorted(successors.get(current, ())):
            visited_expansions += 1
            if visited_expansions > bound * max(1, len(world.actions)):
                truncated = True
                break
            if nxt not in depths:
                depths[nxt] = depth + 1
                queue.append(nxt)
        if truncated and visited_expansions > bound * max(1, len(world.actions)):
            break

    return ReachabilityResult(
        reachable_actions=set(depths),
        depths=depths,
        bound=bound,
        truncated=truncated,
    )


def _check_reference_integrity(world: WorldDefinition, report: DiagnosticReport) -> None:
    """Walk IR edges that validate_world may not fully cover for analysis depth."""
    action_ids = {a.id for a in world.actions}
    state_ids = {s.id for s in world.state}
    observation_ids = {o.id for o in world.observations}
    failure_ids = {f.id for f in world.failures}

    for action in world.actions:
        if action.compensation_action and action.compensation_action not in action_ids:
            report.add(
                make_diagnostic(
                    "EAC3002",
                    reason=(
                        f"action {action.id!r} compensation_action "
                        f"{action.compensation_action!r} is unknown"
                    ),
                    subject=action.id,
                    affected_artifacts=[f"action:{action.id}"],
                )
            )
        for fid in action.failure_ids:
            if fid not in failure_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"action {action.id!r} references unknown failure {fid!r}",
                        subject=action.id,
                    )
                )
        for path in [*action.reads, *action.writes]:
            root = path.split(".", 1)[0]
            if root not in state_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"action {action.id!r} references unknown state {root!r}",
                        subject=action.id,
                    )
                )

    for transition in world.transitions:
        if transition.action_id not in action_ids:
            report.add(
                make_diagnostic(
                    "EAC3002",
                    reason=(
                        f"transition {transition.id!r} references unknown action "
                        f"{transition.action_id!r}"
                    ),
                    subject=transition.id,
                )
            )
        for branch in transition.branches:
            if branch.observation and branch.observation not in observation_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=(
                            f"transition branch {branch.id!r} references unknown "
                            f"observation {branch.observation!r}"
                        ),
                        subject=transition.id,
                    )
                )
            if transition.kind == "stochastic" and branch.probability is None:
                report.add(
                    make_diagnostic(
                        "EAC4001",
                        reason=(
                            f"stochastic transition {transition.id!r} branch "
                            f"{branch.id!r} lacks probability"
                        ),
                        subject=transition.id,
                    )
                )
        if transition.kind == "stochastic" and transition.branches:
            probs = [b.probability for b in transition.branches if b.probability is not None]
            if probs and abs(sum(probs) - 1.0) > 1e-6:
                report.add(
                    make_diagnostic(
                        "EAC4001",
                        reason=(
                            f"stochastic transition {transition.id!r} probabilities "
                            f"sum to {sum(probs):.6f}, expected 1.0"
                        ),
                        subject=transition.id,
                    )
                )


def _check_mutation_scopes(world: WorldDefinition, report: DiagnosticReport) -> None:
    """Enforce declared mutation_authority against action writes."""
    state_index = world.index_state()
    for action in world.actions:
        for path in action.writes:
            root = path.split(".", 1)[0]
            var = state_index.get(root)
            if var is None:
                continue
            if var.mutability == "immutable":
                report.add(
                    make_diagnostic(
                        "EAC4008",
                        reason=(f"action {action.id!r} writes immutable state {var.id!r}"),
                        subject=action.id,
                        details={"state_id": var.id, "path": path},
                        affected_artifacts=[f"action:{action.id}", f"state:{var.id}"],
                    )
                )
                continue
            if not var.mutation_authority:
                continue
            allowed = set(var.mutation_authority)
            if action.id not in allowed and not (set(action.actor_classes) & allowed):
                report.add(
                    make_diagnostic(
                        "EAC4008",
                        reason=(
                            f"action {action.id!r} writes {var.id!r} outside "
                            f"mutation_authority {sorted(allowed)}"
                        ),
                        subject=action.id,
                        details={
                            "state_id": var.id,
                            "path": path,
                            "mutation_authority": sorted(allowed),
                        },
                        affected_artifacts=[f"action:{action.id}", f"state:{var.id}"],
                    )
                )


def _check_unreachable_actions(
    world: WorldDefinition,
    reachability: ReachabilityResult,
    report: DiagnosticReport,
) -> None:
    """Flag declared actions that never appear in the reachable set."""
    for action in world.actions:
        if action.id in reachability.reachable_actions:
            continue
        report.add(
            make_diagnostic(
                "EAC4009",
                reason=(
                    f"action {action.id!r} is unreachable from actor seeds within "
                    f"BFS bound {reachability.bound}"
                ),
                subject=action.id,
                details={"truncated": reachability.truncated},
                affected_artifacts=[f"action:{action.id}"],
            )
        )


def _check_precondition_guards(world: WorldDefinition, report: DiagnosticReport) -> None:
    """Validate precondition / guard expressions reference known state."""
    state_ids = {s.id for s in world.state}
    dotted = re.compile(r"\bstate\.([A-Za-z_][A-Za-z0-9_]*)\b")

    def _unknown_refs(expression: str, structured: dict[str, Any] | None) -> list[str]:
        bad: set[str] = set()
        for match in dotted.finditer(expression):
            if match.group(1) not in state_ids:
                bad.add(match.group(1))
        # Bare state id tokens that appear as left-hand sides: `on_hand >= 0`
        for sid_candidate in re.findall(r"\b([a-z][a-z0-9_]*)\b", expression):
            if sid_candidate in state_ids:
                continue
            # Only flag when another known state shares a prefix pattern and this
            # looks like a typo of a declared id (edit distance deferred — catalogued).
            if any(
                sid_candidate.startswith(s) or s.startswith(sid_candidate)
                for s in state_ids
                if abs(len(s) - len(sid_candidate)) <= 2 and s != sid_candidate
            ):
                # Skip soft fuzzy matches; require explicit structured or state. prefix.
                pass
        if structured:
            for key in ("state_id", "var", "variable"):
                val = structured.get(key)
                if isinstance(val, str) and val and val not in state_ids:
                    bad.add(val)
            left = structured.get("left")
            if isinstance(left, str) and left.startswith("state."):
                sid = left.split(".", 1)[1]
                if sid not in state_ids:
                    bad.add(sid)
        return sorted(bad)

    for action in world.actions:
        for pre in action.preconditions:
            bad = _unknown_refs(pre.expression, pre.structured)
            if bad:
                report.add(
                    make_diagnostic(
                        "EAC4010",
                        reason=(
                            f"action {action.id!r} precondition references unknown state {bad}"
                        ),
                        subject=action.id,
                        details={"expression": pre.expression, "unknown": bad},
                    )
                )

    for transition in world.transitions:
        if transition.guard is None:
            continue
        bad = _unknown_refs(transition.guard.expression, transition.guard.structured)
        if bad:
            report.add(
                make_diagnostic(
                    "EAC4010",
                    reason=(f"transition {transition.id!r} guard references unknown state {bad}"),
                    subject=transition.id,
                    details={"expression": transition.guard.expression, "unknown": bad},
                )
            )


def _check_solvability(
    world: WorldDefinition,
    reachability: ReachabilityResult,
    report: DiagnosticReport,
) -> None:
    action_index = world.index_actions()
    writers = _state_writers(world)
    for task in world.tasks:
        required = _actions_implied_by_task(task, action_index)
        # Goal claims like "backlog == 0" require a reachable writer of that state.
        for claim in task.goal_claims:
            for state_id in _state_ids_in_claim(claim, {s.id for s in world.state}):
                claim_writers = writers.get(state_id, set())
                if not claim_writers:
                    report.add(
                        make_diagnostic(
                            "EAC4002",
                            reason=(
                                f"task {task.id!r} goal {claim!r} references state "
                                f"{state_id!r} with no writers"
                            ),
                            subject=task.id,
                            details={"state_id": state_id, "claim": claim},
                        )
                    )
                    continue
                if not (claim_writers & reachability.reachable_actions):
                    report.add(
                        make_diagnostic(
                            "EAC4002",
                            reason=(
                                f"task {task.id!r} goal {claim!r} needs writers of "
                                f"{state_id!r} but none are reachable: "
                                f"{sorted(claim_writers)}"
                            ),
                            subject=task.id,
                            details={
                                "state_id": state_id,
                                "writers": sorted(claim_writers),
                                "truncated": reachability.truncated,
                            },
                        )
                    )
                else:
                    required |= claim_writers & {
                        a
                        for a in claim_writers
                        if a in task.permitted_tools or not task.permitted_tools
                    }

        missing = sorted(a for a in required if a not in reachability.reachable_actions)
        if missing:
            report.add(
                make_diagnostic(
                    "EAC4002",
                    reason=(
                        f"task {task.id!r} depends on unreachable actions "
                        f"{missing} within BFS bound {reachability.bound}"
                    ),
                    subject=task.id,
                    details={"missing_actions": missing, "truncated": reachability.truncated},
                )
            )
        elif task.horizon is not None and task.horizon <= 0:
            report.add(
                make_diagnostic(
                    "EAC4002",
                    reason=f"task {task.id!r} has non-positive horizon {task.horizon}",
                    subject=task.id,
                )
            )
        # Horizon vs required path depth (lower bound from BFS depths).
        if task.horizon is not None and required:
            depths = [reachability.depths[a] for a in required if a in reachability.depths]
            if depths and max(depths) > task.horizon:
                report.add(
                    make_diagnostic(
                        "EAC4002",
                        reason=(
                            f"task {task.id!r} horizon {task.horizon} is below "
                            f"BFS depth {max(depths)} of required actions"
                        ),
                        subject=task.id,
                        details={"required_depth": max(depths), "horizon": task.horizon},
                    )
                )
        for role, actor_id in task.actor_assignment.items():
            if actor_id not in world.index_actors() and actor_id not in {
                a.actor_class for a in world.actors
            }:
                report.add(
                    make_diagnostic(
                        "EAC4002",
                        reason=(
                            f"task {task.id!r} assigns role {role!r} to unknown "
                            f"actor/class {actor_id!r}"
                        ),
                        subject=task.id,
                    )
                )


def _state_writers(world: WorldDefinition) -> dict[str, set[str]]:
    writers: dict[str, set[str]] = {}
    for action in world.actions:
        for path in action.writes:
            writers.setdefault(path.split(".", 1)[0], set()).add(action.id)
    return writers


def _state_ids_in_claim(claim: str, state_ids: set[str]) -> set[str]:
    found: set[str] = set()
    for sid in state_ids:
        if re.search(rf"\b{re.escape(sid)}\b", claim):
            found.add(sid)
    return found


def _actions_implied_by_task(
    task: TaskTemplate,
    action_index: dict[str, ActionContract],
) -> set[str]:
    """Derive required actions from permitted_tools and named goal/process text."""
    implied: set[str] = set(task.permitted_tools)
    haystacks = [
        task.intent,
        *task.goal_claims,
        *task.process_requirements,
        *task.prohibited_behavior,
    ]
    for action_id in action_index:
        for text in haystacks:
            if action_id in text:
                implied.add(action_id)
    return implied


def _check_reset_integrity(world: WorldDefinition, report: DiagnosticReport) -> None:
    reset = world.reset_semantics.lower()
    for var in world.state:
        if reset in {"full_reset", "episode_reset"} and var.reset_class == "external":
            report.add(
                make_diagnostic(
                    "EAC4003",
                    reason=(
                        f"state {var.id!r} is reset_class=external under "
                        f"reset_semantics={world.reset_semantics!r}"
                    ),
                    subject=var.id,
                )
            )
        if reset == "no_reset" and var.reset_class == "reset_on_episode":
            report.add(
                make_diagnostic(
                    "EAC4003",
                    reason=(f"state {var.id!r} resets on episode but world declares no_reset"),
                    subject=var.id,
                )
            )
        if var.persistence == "durable" and var.reset_class == "reset_on_episode":
            report.add(
                make_diagnostic(
                    "EAC4003",
                    reason=(
                        f"durable state {var.id!r} is marked reset_on_episode "
                        "(likely inconsistency)"
                    ),
                    subject=var.id,
                )
            )
        if (
            reset in {"full_reset", "episode_reset"}
            and var.reset_class == "carry_forward"
            and var.persistence == "ephemeral"
        ):
            report.add(
                make_diagnostic(
                    "EAC4003",
                    reason=(
                        f"ephemeral state {var.id!r} is carry_forward under "
                        f"reset_semantics={world.reset_semantics!r}"
                    ),
                    subject=var.id,
                )
            )


def _check_authority_delegation(world: WorldDefinition, report: DiagnosticReport) -> None:
    actors = list(world.actors)
    action_ids = {a.id for a in world.actions}
    for action in world.actions:
        if not action.authorization:
            continue
        auth = action.authorization
        eligible = [
            actor
            for actor in actors
            if actor.actor_class in action.actor_classes or actor.id in action.actor_classes
        ]
        if not eligible:
            report.add(
                make_diagnostic(
                    "EAC4004",
                    reason=(
                        f"action {action.id!r} requires {auth!r} but no actor belongs "
                        f"to actor_classes {action.actor_classes}"
                    ),
                    subject=action.id,
                    affected_artifacts=[f"action:{action.id}"],
                )
            )
            continue
        dischargers = [actor for actor in eligible if _actor_discharges(auth, actor)]
        if not dischargers:
            report.add(
                make_diagnostic(
                    "EAC4004",
                    reason=(
                        f"action {action.id!r} requires {auth!r} but no eligible actor "
                        "declares matching authority, role, capability, or delegation"
                    ),
                    subject=action.id,
                    affected_artifacts=[f"action:{action.id}"],
                )
            )
            continue
        # Stronger check: at least one discharger must list the action as available
        # when available_actions is non-empty for that actor.
        avail_checked = [a for a in dischargers if a.available_actions]
        if avail_checked and not any(action.id in a.available_actions for a in avail_checked):
            report.add(
                make_diagnostic(
                    "EAC4004",
                    reason=(
                        f"action {action.id!r} is authorized for "
                        f"{[a.id for a in dischargers]} but not listed in their "
                        "available_actions"
                    ),
                    subject=action.id,
                    details={
                        "dischargers": [a.id for a in dischargers],
                        "authorization": auth,
                    },
                    affected_artifacts=[f"action:{action.id}"],
                )
            )

    # Orphan delegation targets that reference unknown roles/actions.
    known_auth_tokens: set[str] = set()
    for action in world.actions:
        if action.authorization:
            known_auth_tokens.add(_normalize_auth_token(action.authorization))
    for actor in actors:
        for rule in actor.delegation_rules:
            for target in _delegation_targets(rule):
                if (
                    target
                    and target not in known_auth_tokens
                    and target not in {_normalize_auth_token(r) for r in actor.roles}
                ):
                    # Soft note via EAC4004 only when rule looks like action delegation.
                    if target in action_ids:
                        continue
                    if rule.lower().startswith(("delegates:", "via:", "grant:")):
                        report.add(
                            make_diagnostic(
                                "EAC4004",
                                reason=(
                                    f"actor {actor.id!r} delegation_rule {rule!r} "
                                    f"targets unknown authority token {target!r}"
                                ),
                                subject=actor.id,
                                details={"delegation_rule": rule, "target": target},
                            )
                        )


def _check_information_flow(world: WorldDefinition, report: DiagnosticReport) -> None:
    """Detect evaluator leaks and declared information-flow mapping defects."""
    state_index = world.index_state()
    evaluator_only = {s.id for s in world.state if s.evaluator_visible and not s.policy_visible}
    for obs in world.observations:
        visible_roots = {path.split(".", 1)[0] for path in obs.visible_paths}
        omitted_roots = {path.split(".", 1)[0] for path in obs.omitted_paths}
        overlap = sorted(visible_roots & omitted_roots)
        if overlap:
            report.add(
                make_diagnostic(
                    "EAC5003",
                    reason=(
                        f"observation {obs.id!r} lists paths as both visible and omitted: {overlap}"
                    ),
                    subject=obs.id,
                    details={"overlap": overlap},
                    affected_artifacts=[f"observation:{obs.id}"],
                )
            )
        # Evaluator-only state must be omitted (or absent) from policy observations.
        leaked_hidden = sorted(visible_roots & evaluator_only)
        for state_id in leaked_hidden:
            report.add(
                make_diagnostic(
                    "EAC5002",
                    state_id=state_id,
                    observation_id=obs.id,
                    subject=obs.id,
                    details={"path": state_id, "evaluator_only": True},
                    affected_artifacts=[f"observation:{obs.id}", f"state:{state_id}"],
                )
            )
        undeclared_hidden = sorted(
            sid for sid in evaluator_only if sid not in omitted_roots and sid not in visible_roots
        )
        if undeclared_hidden and obs.target_actor_class not in {None, "evaluator", "oracle"}:
            report.add(
                make_diagnostic(
                    "EAC5003",
                    reason=(
                        f"observation {obs.id!r} does not omit evaluator-only state "
                        f"{undeclared_hidden}"
                    ),
                    subject=obs.id,
                    details={"undeclared_hidden": undeclared_hidden},
                )
            )

        for label in obs.information_flow_labels:
            if ":" not in label:
                continue
            state_id, _, mapping = label.partition(":")
            var = state_index.get(state_id)
            if var is None:
                report.add(
                    make_diagnostic(
                        "EAC5003",
                        reason=(
                            f"observation {obs.id!r} information_flow_labels "
                            f"reference unknown state {state_id!r}"
                        ),
                        subject=obs.id,
                        details={"label": label},
                    )
                )
                continue
            mapping_l = mapping.lower()
            if mapping_l in {"deny", "omit", "hidden"} and state_id in visible_roots:
                report.add(
                    make_diagnostic(
                        "EAC5003",
                        reason=(
                            f"observation {obs.id!r} maps {state_id!r} as {mapping!r} "
                            "but includes it in visible_paths"
                        ),
                        subject=obs.id,
                        details={"label": label, "state_id": state_id},
                    )
                )
            if mapping_l in {"policy", "policy_visible"} and not var.policy_visible:
                report.add(
                    make_diagnostic(
                        "EAC5003",
                        reason=(
                            f"observation {obs.id!r} declares {state_id!r} as policy "
                            "but state.policy_visible is False"
                        ),
                        subject=obs.id,
                        details={"label": label, "state_id": state_id},
                    )
                )

        for path in obs.visible_paths:
            root = path.split(".", 1)[0]
            var = state_index.get(root)
            if var is None:
                report.add(
                    make_diagnostic(
                        "EAC5001",
                        reason=(f"observation {obs.id!r} visible path unknown state {root!r}"),
                        subject=obs.id,
                    )
                )
                continue
            if var.evaluator_visible and not var.policy_visible:
                report.add(
                    make_diagnostic(
                        "EAC5002",
                        state_id=var.id,
                        observation_id=obs.id,
                        subject=obs.id,
                        details={
                            "path": path,
                            "evaluator_visible": True,
                            "policy_visible": False,
                        },
                        affected_artifacts=[f"observation:{obs.id}", f"state:{var.id}"],
                    )
                )
            if (
                var.confidentiality in {"confidential", "restricted"}
                and var.policy_visible
                and not obs.access_control
            ):
                report.add(
                    make_diagnostic(
                        "EAC5003",
                        reason=(
                            f"observation {obs.id!r} exposes "
                            f"confidentiality={var.confidentiality!r} state "
                            f"{var.id!r} without access_control"
                        ),
                        subject=obs.id,
                        details={"state_id": var.id, "confidentiality": var.confidentiality},
                    )
                )

    # Actions that read evaluator-only state into actor_classes without evaluator role.
    for action in world.actions:
        for path in action.reads:
            root = path.split(".", 1)[0]
            if root not in evaluator_only:
                continue
            if any(cls in {"evaluator", "oracle"} for cls in action.actor_classes):
                continue
            report.add(
                make_diagnostic(
                    "EAC5003",
                    reason=(
                        f"action {action.id!r} reads evaluator-only state {root!r} "
                        f"for actor_classes {action.actor_classes}"
                    ),
                    subject=action.id,
                    details={"state_id": root, "actor_classes": list(action.actor_classes)},
                )
            )


def _check_resource_conservation(world: WorldDefinition, report: DiagnosticReport) -> None:
    counters = {s.id for s in world.state if s.type == "resource_counter"}
    if not counters:
        return
    for action in world.actions:
        touched = [w.split(".", 1)[0] for w in action.writes if w.split(".", 1)[0] in counters]
        if touched and not action.resource_effects:
            report.add(
                make_diagnostic(
                    "EAC4005",
                    reason=(
                        f"action {action.id!r} writes resource_counter(s) {touched} "
                        "without resource_effects"
                    ),
                    subject=action.id,
                )
            )


def _check_transaction_retry(world: WorldDefinition, report: DiagnosticReport) -> None:
    action_ids = {a.id for a in world.actions}
    failure_index = {f.id: f for f in world.failures}
    for action in world.actions:
        if action.timeout_behavior is not None and action.retry_behavior is None:
            report.add(
                make_diagnostic(
                    "EAC4027",
                    action_id=action.id,
                    subject=action.id,
                    affected_artifacts=[f"action:{action.id}"],
                )
            )
            report.add(
                make_diagnostic(
                    "EAC4006",
                    reason=(
                        f"action {action.id!r} declares timeout_behavior without retry_behavior"
                    ),
                    subject=action.id,
                )
            )
        if action.compensation_action and not action.transaction_boundary:
            report.add(
                make_diagnostic(
                    "EAC4006",
                    reason=(
                        f"action {action.id!r} has compensation_action but no transaction_boundary"
                    ),
                    subject=action.id,
                )
            )
        if (
            action.compensation_action
            and action.compensation_action not in action_ids
            and action.compensation_action is not None
        ):
            pass
        if action.compensation_action and action.compensation_action in action_ids:
            # Compensation should itself be reachable / declared for same actor classes.
            comp = next(a for a in world.actions if a.id == action.compensation_action)
            if (
                action.actor_classes
                and comp.actor_classes
                and not (set(action.actor_classes) & set(comp.actor_classes))
            ):
                report.add(
                    make_diagnostic(
                        "EAC4006",
                        reason=(
                            f"action {action.id!r} compensation "
                            f"{action.compensation_action!r} has disjoint "
                            f"actor_classes {comp.actor_classes}"
                        ),
                        subject=action.id,
                    )
                )
        if action.retry_behavior and action.idempotency is None:
            report.add(
                make_diagnostic(
                    "EAC4006",
                    reason=(f"action {action.id!r} is retryable but idempotency is unset"),
                    subject=action.id,
                )
            )
        if action.transaction_boundary and not action.failure_ids:
            report.add(
                make_diagnostic(
                    "EAC4006",
                    reason=(
                        f"action {action.id!r} declares transaction_boundary without "
                        "failure_ids covering abort/partial paths"
                    ),
                    subject=action.id,
                )
            )
        if (
            action.retry_behavior
            and action.timeout_behavior is None
            and any(
                failure_index[fid].category == "timeout"
                for fid in action.failure_ids
                if fid in failure_index
            )
        ):
            report.add(
                make_diagnostic(
                    "EAC4006",
                    reason=(
                        f"action {action.id!r} has retry_behavior and timeout failures "
                        "but timeout_behavior is unset"
                    ),
                    subject=action.id,
                )
            )
        for fid in action.failure_ids:
            failure = failure_index.get(fid)
            if failure is None:
                continue
            if failure.retryable and action.retry_behavior is None:
                report.add(
                    make_diagnostic(
                        "EAC4006",
                        reason=(
                            f"action {action.id!r} references retryable failure {fid!r} "
                            "but retry_behavior is unset"
                        ),
                        subject=action.id,
                        details={"failure_id": fid},
                    )
                )
            if (
                failure.transaction_effect in {"partial", "abort"}
                and not action.transaction_boundary
            ):
                report.add(
                    make_diagnostic(
                        "EAC4006",
                        reason=(
                            f"action {action.id!r} failure {fid!r} has "
                            f"transaction_effect={failure.transaction_effect!r} "
                            "without action.transaction_boundary"
                        ),
                        subject=action.id,
                        details={"failure_id": fid},
                    )
                )
            if (
                failure.transaction_effect == "partial"
                and action.compensation_action is None
                and action.transaction_boundary
            ):
                report.add(
                    make_diagnostic(
                        "EAC4006",
                        reason=(
                            f"action {action.id!r} failure {fid!r} is partial under "
                            "transaction_boundary but compensation_action is unset"
                        ),
                        subject=action.id,
                        details={"failure_id": fid},
                    )
                )


def _check_termination_integrity(world: WorldDefinition, report: DiagnosticReport) -> None:
    terminal_branches = [(t.id, b.id) for t in world.transitions for b in t.branches if b.terminal]
    term = world.termination_semantics.lower()
    if "goal" in term or "horizon" in term:
        if world.tasks and not terminal_branches and term not in {"horizon", "goal_or_horizon"}:
            report.add(
                make_diagnostic(
                    "EAC4007",
                    reason=(
                        f"termination_semantics={world.termination_semantics!r} but no "
                        "terminal transition branches are declared"
                    ),
                    subject=world.environment_id,
                )
            )
        for task in world.tasks:
            if task.horizon is None and "horizon" in term and "goal" not in term:
                report.add(
                    make_diagnostic(
                        "EAC4007",
                        reason=(
                            f"task {task.id!r} missing horizon under "
                            f"termination_semantics={world.termination_semantics!r}"
                        ),
                        subject=task.id,
                    )
                )
            if term in {"goal", "goal_only"} and task.horizon is not None and not terminal_branches:
                report.add(
                    make_diagnostic(
                        "EAC4007",
                        reason=(
                            f"task {task.id!r} under goal termination has a horizon but "
                            "no terminal transition branches"
                        ),
                        subject=task.id,
                    )
                )

    if term in {"never", "none", "unterminated"} and terminal_branches:
        report.add(
            make_diagnostic(
                "EAC4007",
                reason=(
                    f"termination_semantics={world.termination_semantics!r} but terminal "
                    f"branches exist: {terminal_branches}"
                ),
                subject=world.environment_id,
            )
        )
