"""Event-sourced AssuredEnvironment reference implementation."""

from __future__ import annotations

import copy
import random
import uuid
from typing import Any

from envassure.canonical import canonical_hash
from envassure.ir.models import (
    ActionContract,
    ActorDefinition,
    TransitionBranch,
    TransitionRule,
    WorldDefinition,
)
from envassure.ir.primitives import DeterminismClass
from envassure.runtime.effects import apply_effect, coerce_literal, evaluate_constraint
from envassure.runtime.events import Event, SideEffectIntent, StepResult
from envassure.runtime.snapshot import Snapshot


class RuntimeError_(RuntimeError):
    """Runtime protocol / integrity violation."""


class StrictMutationError(RuntimeError_):
    """Raised when out-of-band mutation is attempted in strict mode."""


class EventSourcedEnvironment:
    """Validate → transition → emit events/intents → atomic apply (ADR-0002)."""

    def __init__(
        self,
        world: WorldDefinition,
        *,
        strict: bool = True,
        live_external_effects: bool = False,
        default_actor_id: str | None = None,
    ) -> None:
        self._world = world.model_copy(deep=True)
        self._strict = strict
        self._live_external_effects = live_external_effects
        self._actions = self._world.index_actions()
        self._actors_ir = self._world.index_actors()
        self._observations = {o.id: o for o in self._world.observations}
        self._failures = {f.id: f for f in self._world.failures}
        self._transitions_by_action: dict[str, list[TransitionRule]] = {}
        for rule in self._world.transitions:
            self._transitions_by_action.setdefault(rule.action_id, []).append(rule)
        for rules in self._transitions_by_action.values():
            rules.sort(key=lambda r: (-r.priority, r.id))

        self._default_actor_id = default_actor_id or (
            self._world.actors[0].id if self._world.actors else None
        )
        self._authoritative_state: dict[str, Any] = {}
        self._actor_runtime: dict[str, dict[str, Any]] = {}
        self._scheduled_events: list[Event] = []
        self._stubs: dict[str, Any] = {}
        self._clock = 0
        self._sequence = 0
        self._seed: int | None = None
        self._rng = random.Random(0)
        self._audit_head = ""
        self._event_log: list[Event] = []
        self._recorded_intents: list[SideEffectIntent] = []
        self._task_state: dict[str, Any] = {}
        self._pending_transactions: list[dict[str, Any]] = []
        self._episode_id: str | None = None
        self._terminal = False
        self._initialized = False
        self._state_fingerprint: str | None = None

    @property
    def world(self) -> WorldDefinition:
        return self._world

    @property
    def determinism(self) -> DeterminismClass:
        return self._world.determinism

    @property
    def strict(self) -> bool:
        return self._strict

    @property
    def live_external_effects(self) -> bool:
        return self._live_external_effects

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = options or {}
        self._check_strict_integrity()
        if seed is None:
            seed = int(options.get("seed", 0))
        self._seed = seed
        self._rng = random.Random(seed)
        self._episode_id = str(options.get("episode_id") or uuid.uuid4())
        self._clock = 0
        self._sequence = 0
        self._audit_head = ""
        self._event_log = []
        self._recorded_intents = []
        self._scheduled_events = []
        self._stubs = dict(options.get("stubs") or {})
        self._pending_transactions = []
        self._terminal = False
        self._task_state = {
            "task_id": options.get("task_id"),
            "steps": 0,
            "horizon": None,
        }
        task_id = options.get("task_id")
        if isinstance(task_id, str):
            for task in self._world.tasks:
                if task.id == task_id:
                    self._task_state["horizon"] = task.horizon
                    break

        self._authoritative_state = self._initial_state(options.get("initial_state"))
        self._actor_runtime = {
            actor.id: {
                "id": actor.id,
                "actor_class": actor.actor_class,
                "roles": list(actor.roles),
                "capabilities": list(actor.capabilities),
                "credentials": list(actor.credentials),
                "available_actions": list(actor.available_actions),
                "observation_projection_id": actor.observation_projection_id,
            }
            for actor in self._world.actors
        }
        self._initialized = True
        self._refresh_fingerprint()
        if self._default_actor_id:
            return self.observe(self._default_actor_id)
        return copy.deepcopy(self._authoritative_state)

    def step(
        self,
        actor_id: str,
        action_id: str,
        payload: dict[str, Any] | None = None,
    ) -> StepResult:
        self._ensure_initialized()
        self._check_strict_integrity()
        payload = payload or {}

        if self._terminal:
            return StepResult(
                ok=False,
                observation=self.observe(actor_id),
                failure_id="episode_terminal",
                failure_category="business_rule",
                info={"reason": "episode already terminal"},
                terminal=True,
            )

        actor = self._actors_ir.get(actor_id)
        if actor is None:
            return self._reject(
                actor_id,
                action_id,
                failure_id="unknown_actor",
                category="validation",
                reason=f"unknown actor {actor_id!r}",
            )

        action = self._actions.get(action_id)
        if action is None:
            return self._reject(
                actor_id,
                action_id,
                failure_id="unknown_action",
                category="validation",
                reason=f"unknown action {action_id!r}",
            )

        if action_id not in actor.available_actions and actor.available_actions:
            return self._reject(
                actor_id,
                action_id,
                failure_id="action_not_available",
                category="validation",
                reason=f"action {action_id!r} not available to actor {actor_id!r}",
            )

        if action.actor_classes and actor.actor_class not in action.actor_classes:
            return self._reject(
                actor_id,
                action_id,
                failure_id="actor_class_mismatch",
                category="authorization",
                reason=(
                    f"actor class {actor.actor_class!r} not permitted for action {action_id!r}"
                ),
            )

        actor_view = self._actor_runtime[actor_id]
        auth_failure = self._check_authorization(action, actor, actor_view)
        if auth_failure is not None:
            return auth_failure

        precond_failure = self._check_preconditions(action, actor_view)
        if precond_failure is not None:
            return precond_failure

        rule = self._select_transition(action_id, actor_view)
        if rule is None:
            return self._reject(
                actor_id,
                action_id,
                failure_id="no_transition",
                category="business_rule",
                reason=f"no transition rule for action {action_id!r}",
            )

        branch = self._select_branch(rule)
        if branch is None:
            return self._reject(
                actor_id,
                action_id,
                failure_id="no_branch",
                category="business_rule",
                reason=f"no branch selected for rule {rule.id!r}",
            )

        # Stage effects on a working copy; commit atomically.
        working = copy.deepcopy(self._authoritative_state)
        write_map: dict[str, Any] = {}
        try:
            for effect in action.intended_effects:
                write_map.update(apply_effect(working, effect))
        except ValueError as exc:
            return self._reject(
                actor_id,
                action_id,
                failure_id="effect_error",
                category="business_rule",
                reason=str(exc),
            )

        self._clock += 1
        events: list[Event] = []
        for event_type in branch.events:
            self._sequence += 1
            event = Event(
                id=f"evt-{self._sequence}",
                type=event_type,
                sequence=self._sequence,
                clock=self._clock,
                actor_id=actor_id,
                action_id=action_id,
                branch_id=branch.id,
                payload=copy.deepcopy(payload),
                writes=copy.deepcopy(write_map),
            )
            events.append(event)
            self._event_log.append(event)
            self._audit_head = canonical_hash(
                {
                    "prev": self._audit_head,
                    "event": event.model_dump(mode="json"),
                }
            )

        intents: list[SideEffectIntent] = []
        intent_names = list(branch.side_effect_intents) or list(action.external_side_effects)
        for idx, kind in enumerate(intent_names):
            intent = SideEffectIntent(
                id=f"sei-{self._sequence}-{idx}",
                kind=kind,
                target=None,
                payload={"action_id": action_id, "actor_id": actor_id},
                executed=False,
                recorded_only=not self._live_external_effects,
            )
            if self._live_external_effects:
                intent.executed = True
                intent.recorded_only = False
            intents.append(intent)
            self._recorded_intents.append(intent)

        # Atomic commit
        self._authoritative_state = working
        self._task_state["steps"] = int(self._task_state.get("steps", 0)) + 1
        horizon = self._task_state.get("horizon")
        truncated = False
        terminal = bool(branch.terminal)
        if isinstance(horizon, int) and self._task_state["steps"] >= horizon:
            truncated = True
            terminal = True
        if self._goal_reached():
            terminal = True
        self._terminal = terminal
        self._refresh_fingerprint()

        evidence = [
            {"kind": e, "action_id": action_id, "sequence": self._sequence}
            for e in (rule.emitted_evidence or action.evidence_emitted)
        ]
        observation = self.observe(actor_id)
        return StepResult(
            ok=True,
            events=events,
            side_effect_intents=intents,
            observation=observation,
            evidence=evidence,
            terminal=terminal,
            truncated=truncated,
            info={
                "rule_id": rule.id,
                "branch_id": branch.id,
                "determinism": self._world.determinism,
            },
            state_digest=self._digests()["state"],
        )

    def state(self) -> dict[str, Any]:
        self._ensure_initialized()
        self._check_strict_integrity()
        # Always return a deep copy so callers cannot mutate authoritative state.
        return copy.deepcopy(self._authoritative_state)

    def observe(self, actor_id: str) -> dict[str, Any]:
        self._ensure_initialized()
        self._check_strict_integrity()
        actor = self._actors_ir.get(actor_id)
        if actor is None:
            raise KeyError(f"unknown actor {actor_id!r}")
        state_copy = copy.deepcopy(self._authoritative_state)
        proj_id = actor.observation_projection_id
        if not proj_id or proj_id not in self._observations:
            return state_copy
        proj = self._observations[proj_id]
        if proj.visible_paths:
            return {k: state_copy[k] for k in proj.visible_paths if k in state_copy}
        result = state_copy
        for path in proj.omitted_paths:
            result.pop(path, None)
        return result

    def snapshot(self) -> Snapshot:
        self._ensure_initialized()
        self._check_strict_integrity()
        return Snapshot(
            environment_id=self._world.environment_id,
            sequence=self._sequence,
            authoritative_state=copy.deepcopy(self._authoritative_state),
            actors=copy.deepcopy(self._actor_runtime),
            scheduled_events=copy.deepcopy(self._scheduled_events),
            stubs=copy.deepcopy(self._stubs),
            clock=self._clock,
            rng=self._serialize_rng(),
            audit_head=self._audit_head,
            digests=self._digests(),
            task_state=copy.deepcopy(self._task_state),
            pending_transactions=copy.deepcopy(self._pending_transactions),
            event_log=copy.deepcopy(self._event_log),
            recorded_intents=copy.deepcopy(self._recorded_intents),
            seed=self._seed,
            episode_id=self._episode_id,
        )

    def restore(self, snapshot: Snapshot) -> None:
        if snapshot.environment_id != self._world.environment_id:
            raise RuntimeError_(
                f"snapshot environment_id {snapshot.environment_id!r} does not match "
                f"{self._world.environment_id!r}"
            )
        self._authoritative_state = copy.deepcopy(snapshot.authoritative_state)
        self._actor_runtime = copy.deepcopy(snapshot.actors)
        self._scheduled_events = copy.deepcopy(snapshot.scheduled_events)
        self._stubs = copy.deepcopy(snapshot.stubs)
        self._clock = snapshot.clock
        self._sequence = snapshot.sequence
        self._audit_head = snapshot.audit_head
        self._task_state = copy.deepcopy(snapshot.task_state)
        self._pending_transactions = copy.deepcopy(snapshot.pending_transactions)
        self._event_log = copy.deepcopy(snapshot.event_log)
        self._recorded_intents = copy.deepcopy(snapshot.recorded_intents)
        self._seed = snapshot.seed
        self._episode_id = snapshot.episode_id
        self._restore_rng(snapshot.rng)
        self._terminal = bool(self._task_state.get("terminal", False))
        self._initialized = True
        self._refresh_fingerprint()

    def fork(self) -> EventSourcedEnvironment:
        snap = self.snapshot()
        child = EventSourcedEnvironment(
            self._world,
            strict=self._strict,
            live_external_effects=self._live_external_effects,
            default_actor_id=self._default_actor_id,
        )
        child.restore(snap)
        return child

    def mutate_state(self, updates: dict[str, Any]) -> None:
        """Out-of-band mutation entrypoint — forbidden in strict mode."""
        if self._strict:
            raise StrictMutationError(
                "strict mode forbids out-of-band state mutation; use step() or restore()"
            )
        self._ensure_initialized()
        self._authoritative_state.update(updates)
        self._refresh_fingerprint()

    # --- internals ---------------------------------------------------------

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError_("environment not reset; call reset() first")

    def _refresh_fingerprint(self) -> None:
        self._state_fingerprint = canonical_hash(self._authoritative_state)

    def _check_strict_integrity(self) -> None:
        if not self._strict or not self._initialized:
            return
        current = canonical_hash(self._authoritative_state)
        if self._state_fingerprint is not None and current != self._state_fingerprint:
            raise StrictMutationError(
                "authoritative state was mutated out-of-band under strict mode"
            )

    def _initial_state(self, override: Any) -> dict[str, Any]:
        state: dict[str, Any] = {}
        for var in self._world.state:
            if var.initial_generator is not None:
                state[var.id] = coerce_literal(var.initial_generator)
            elif var.type == "resource_counter":
                state[var.id] = 0
            elif var.type == "enum" and var.enum_values:
                state[var.id] = var.enum_values[0]
            elif var.type in {"list", "set", "queue"}:
                state[var.id] = []
            elif var.type == "map":
                state[var.id] = {}
            else:
                state[var.id] = None
        if isinstance(override, dict):
            state.update(copy.deepcopy(override))
        return state

    def _check_authorization(
        self,
        action: ActionContract,
        actor: ActorDefinition,
        actor_view: dict[str, Any],
    ) -> StepResult | None:
        auth = action.authorization
        if not auth:
            return None
        if auth.startswith("role:"):
            role = auth.split(":", 1)[1]
            roles = actor_view.get("roles") or actor.roles
            if role not in roles:
                failure_id = action.failure_ids[0] if action.failure_ids else "unauthorized"
                category = "authorization"
                if failure_id in self._failures:
                    category = self._failures[failure_id].category
                return self._reject(
                    actor.id,
                    action.id,
                    failure_id=failure_id,
                    category=category,
                    reason=f"actor lacks required role {role!r}",
                )
        return None

    def _check_preconditions(
        self,
        action: ActionContract,
        actor_view: dict[str, Any],
    ) -> StepResult | None:
        for constraint in action.preconditions:
            ok = evaluate_constraint(
                constraint.expression,
                state=self._authoritative_state,
                actor=actor_view,
            )
            if not ok:
                return self._reject(
                    str(actor_view.get("id")),
                    action.id,
                    failure_id="precondition_failed",
                    category="business_rule",
                    reason=f"precondition failed: {constraint.expression}",
                )
        return None

    def _select_transition(
        self,
        action_id: str,
        actor_view: dict[str, Any],
    ) -> TransitionRule | None:
        for rule in self._transitions_by_action.get(action_id, []):
            if rule.guard is None:
                return rule
            if evaluate_constraint(
                rule.guard.expression,
                state=self._authoritative_state,
                actor=actor_view,
            ):
                return rule
        return None

    def _select_branch(self, rule: TransitionRule) -> TransitionBranch | None:
        if not rule.branches:
            return None
        if rule.kind == "deterministic" or self._world.determinism == "fully_deterministic":
            return rule.branches[0]
        # Seeded stochastic selection
        weighted: list[tuple[TransitionBranch, float]] = []
        for branch in rule.branches:
            weight = branch.probability if branch.probability is not None else 1.0
            weighted.append((branch, float(weight)))
        total = sum(w for _, w in weighted)
        if total <= 0:
            return rule.branches[0]
        pick = self._rng.random() * total
        cumulative = 0.0
        for branch, weight in weighted:
            cumulative += weight
            if pick <= cumulative:
                return branch
        return weighted[-1][0]

    def _goal_reached(self) -> bool:
        task_id = self._task_state.get("task_id")
        if not isinstance(task_id, str):
            return False
        for task in self._world.tasks:
            if task.id != task_id:
                continue
            for claim in task.goal_claims:
                if not evaluate_constraint(
                    claim,
                    state=self._authoritative_state,
                    actor={},
                ):
                    return False
            return bool(task.goal_claims)
        return False

    def _serialize_rng(self) -> dict[str, Any]:
        version, mt, gauss = self._rng.getstate()
        return {
            "seed": self._seed,
            "version": version,
            "mt": list(mt),
            "gauss": gauss,
        }

    def _restore_rng(self, payload: dict[str, Any]) -> None:
        seed = payload.get("seed", self._seed)
        self._rng = random.Random(seed if seed is not None else 0)
        mt = payload.get("mt")
        version = payload.get("version")
        if mt is not None and version is not None:
            gauss = payload.get("gauss")
            self._rng.setstate((int(version), tuple(mt), gauss))

    def _digests(self) -> dict[str, str]:
        return {
            "state": canonical_hash(self._authoritative_state),
            "audit_head": self._audit_head or canonical_hash(""),
            "events": canonical_hash([e.model_dump(mode="json") for e in self._event_log]),
        }

    def _reject(
        self,
        actor_id: str,
        action_id: str,
        *,
        failure_id: str,
        category: str,
        reason: str,
    ) -> StepResult:
        observation: dict[str, Any] = {}
        if actor_id in self._actors_ir and self._initialized:
            observation = self.observe(actor_id)
        return StepResult(
            ok=False,
            observation=observation,
            failure_id=failure_id,
            failure_category=category,
            info={"reason": reason, "action_id": action_id, "actor_id": actor_id},
            terminal=False,
        )
