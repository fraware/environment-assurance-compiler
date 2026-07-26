"""Event-sourced AssuredEnvironment reference implementation."""

from __future__ import annotations

import copy
import random
from typing import Any

from envassure import __version__ as RUNTIME_VERSION
from envassure.canonical import canonical_hash
from envassure.expressions.diagnostics import ExpressionError
from envassure.ir.models import (
    ActionContract,
    ActorDefinition,
    TransitionBranch,
    TransitionRule,
    WorldDefinition,
)
from envassure.ir.primitives import IR_VERSION, DeterminismClass
from envassure.runtime.authorization import AuthDecision, evaluate_authorization
from envassure.runtime.effects import apply_effect, coerce_literal, evaluate_constraint
from envassure.runtime.events import (
    Event,
    SideEffectIntent,
    StepResult,
    TerminalRecord,
    TransactionReceipt,
    TransitionDecision,
    reconstruct_state,
    validate_event_log,
)
from envassure.runtime.external import (
    ExternalEffectExecutor,
    SideEffectResult,
    recorded_receipt,
)
from envassure.runtime.intent_ids import (
    canonical_effect_payload_digest,
    make_intent_id,
    make_transaction_id,
    seed_derived_episode_id,
)
from envassure.runtime.observations import (
    CompiledObservation,
    ObservationError,
    compile_observation,
    project_state,
)
from envassure.runtime.outcomes import StepOutcome
from envassure.runtime.payloads import (
    PayloadValidationError,
    payload_digest,
    redact_payload,
    validate_payload,
)
from envassure.runtime.snapshot import SNAPSHOT_SCHEMA_VERSION, Snapshot


class RuntimeError_(RuntimeError):
    """Runtime protocol / integrity violation."""


class StrictMutationError(RuntimeError_):
    """Raised when out-of-band mutation is attempted in strict mode."""


class EventSourcedEnvironment:
    """validate → authorize → preconditions → stage → commit (ADR-0002 / EAC-R05)."""

    def __init__(
        self,
        world: WorldDefinition,
        *,
        strict: bool = True,
        live_external_effects: bool = False,
        default_actor_id: str | None = None,
        external_executor: ExternalEffectExecutor | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> None:
        self._world = world.model_copy(deep=True)
        self._strict = strict
        self._live_external_effects = live_external_effects
        self._external_executor = external_executor
        self._auth_context = dict(auth_context or {})
        self._actions = self._world.index_actions()
        self._actors_ir = self._world.index_actors()
        self._observations = {o.id: o for o in self._world.observations}
        self._compiled_observations: dict[str, CompiledObservation] = {}
        for obs in self._world.observations:
            compiled = compile_observation(obs, strict_unsupported=True)
            if compiled.ok and compiled.compiled is not None:
                self._compiled_observations[obs.id] = compiled.compiled
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
        self._event_head = ""
        self._event_log: list[Event] = []
        self._recorded_intents: list[SideEffectIntent] = []
        self._effect_receipts: list[SideEffectResult] = []
        self._transition_decisions: list[TransitionDecision] = []
        self._task_state: dict[str, Any] = {}
        self._pending_transactions: list[dict[str, Any]] = []
        self._episode_id: str | None = None
        self._initial_state_at_reset: dict[str, Any] = {}
        self._terminal = False
        self._truncated = False
        self._terminal_record: TerminalRecord | None = None
        self._initialized = False
        self._state_fingerprint: str | None = None
        self._world_digest = canonical_hash(self._world.content_dict())
        self._policy_digest = canonical_hash(
            {
                "authorization": [a.authorization for a in self._world.actions],
                "failures": [f.model_dump(mode="json") for f in self._world.failures],
            }
        )
        self._config_digest = canonical_hash(
            {
                "strict": self._strict,
                "live_external_effects": self._live_external_effects,
                "determinism": self._world.determinism,
            }
        )
        if self._live_external_effects and self._external_executor is None:
            raise RuntimeError_(
                "live_external_effects=True requires an injected ExternalEffectExecutor; "
                "refusing to fabricate live execution"
            )

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

    @property
    def terminal_record(self) -> TerminalRecord | None:
        """Durable terminal / truncated artifact for the current episode, if any."""
        return self._terminal_record

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
        episode_opt = options.get("episode_id")
        self._episode_id = (
            str(episode_opt) if episode_opt is not None else seed_derived_episode_id(seed)
        )
        self._clock = 0
        self._sequence = 0
        self._audit_head = ""
        self._event_head = ""
        self._event_log = []
        self._recorded_intents = []
        self._effect_receipts = []
        self._transition_decisions = []
        self._scheduled_events = []
        self._stubs = dict(options.get("stubs") or {})
        self._pending_transactions = []
        self._terminal = False
        self._truncated = False
        self._terminal_record = None
        self._task_state = {
            "task_id": options.get("task_id"),
            "steps": 0,
            "horizon": None,
            "terminal": False,
            "truncated": False,
        }
        if isinstance(options.get("auth_context"), dict):
            self._auth_context = dict(options["auth_context"])
        task_id = options.get("task_id")
        if isinstance(task_id, str):
            for task in self._world.tasks:
                if task.id == task_id:
                    self._task_state["horizon"] = task.horizon
                    break

        self._authoritative_state = self._initial_state(options.get("initial_state"))
        self._initial_state_at_reset = copy.deepcopy(self._authoritative_state)
        actors_opt = options.get("actors")
        actor_overrides: dict[str, Any] = dict(actors_opt) if isinstance(actors_opt, dict) else {}
        self._actor_runtime = {}
        for actor in self._world.actors:
            view = {
                "id": actor.id,
                "actor_class": actor.actor_class,
                "roles": list(actor.roles),
                "capabilities": list(actor.capabilities),
                "credentials": list(actor.credentials),
                "available_actions": list(actor.available_actions),
                "observation_projection_id": actor.observation_projection_id,
                "revocation_rules": list(actor.revocation_rules),
                "delegation_rules": list(actor.delegation_rules),
                "authority_source": actor.authority_source,
            }
            override = actor_overrides.get(actor.id)
            if isinstance(override, dict):
                view.update(copy.deepcopy(override))
            self._actor_runtime[actor.id] = view
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
        payload = dict(payload or {})
        transition_index = self._sequence
        run_id = self._episode_id or seed_derived_episode_id(self._seed or 0)
        tx_id = make_transaction_id(run_id=run_id, transition_index=transition_index)
        seq_start = self._sequence

        if self._terminal:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.TERMINAL,
                reason_code="episode_terminal",
                failure_id="episode_terminal",
                category="business_rule",
                reason="episode already terminal",
                mutate=False,
            )

        actor = self._actors_ir.get(actor_id)
        if actor is None:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.INVALID_INPUT,
                reason_code="unknown_actor",
                failure_id="unknown_actor",
                category="validation",
                reason=f"unknown actor {actor_id!r}",
                mutate=False,
            )

        action = self._actions.get(action_id)
        if action is None:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.INVALID_INPUT,
                reason_code="unknown_action",
                failure_id="unknown_action",
                category="validation",
                reason=f"unknown action {action_id!r}",
                mutate=False,
            )

        # --- validate input ---
        try:
            validate_payload(action.input_schema, payload)
        except PayloadValidationError as exc:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.INVALID_INPUT,
                reason_code=exc.reason_code,
                failure_id="invalid_input",
                category="validation",
                reason=str(exc),
                mutate=False,
            )

        if action_id not in actor.available_actions and actor.available_actions:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.INVALID_INPUT,
                reason_code="action_not_available",
                failure_id="action_not_available",
                category="validation",
                reason=f"action {action_id!r} not available to actor {actor_id!r}",
                mutate=False,
            )

        if action.actor_classes and actor.actor_class not in action.actor_classes:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.DENIED,
                reason_code="actor_class_mismatch",
                failure_id="actor_class_mismatch",
                category="authorization",
                reason=(
                    f"actor class {actor.actor_class!r} not permitted for action {action_id!r}"
                ),
                mutate=False,
            )

        actor_view = self._actor_runtime[actor_id]

        # --- authorize ---
        auth_failure = self._check_authorization(
            action, actor, actor_view, payload, tx_id, seq_start
        )
        if auth_failure is not None:
            return auth_failure

        # --- preconditions ---
        precond_failure = self._check_preconditions(action, actor_view, payload, tx_id, seq_start)
        if precond_failure is not None:
            return precond_failure

        # --- select transition / branch ---
        try:
            rule = self._select_transition(action_id, actor_view, payload)
        except ExpressionError as exc:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.UNSUPPORTED_SEMANTICS,
                reason_code="unsupported_guard",
                failure_id="unsupported_semantics",
                category="business_rule",
                reason=str(exc),
                mutate=False,
            )
        if rule is None:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.PRECONDITION_FAILED,
                reason_code="no_transition",
                failure_id="no_transition",
                category="business_rule",
                reason=f"no transition rule for action {action_id!r}",
                mutate=False,
            )

        branch = self._select_branch(rule)
        if branch is None:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.PRECONDITION_FAILED,
                reason_code="no_branch",
                failure_id="no_branch",
                category="business_rule",
                reason=f"no branch selected for rule {rule.id!r}",
                mutate=False,
            )

        # --- stage events / effects on a working copy ---
        working = copy.deepcopy(self._authoritative_state)
        write_map: dict[str, Any] = {}
        eval_context = {
            "clock": self._clock,
            "sequence": self._sequence,
            "episode_id": self._episode_id,
            **self._auth_context,
        }
        try:
            for effect in action.intended_effects:
                write_map.update(
                    apply_effect(
                        working,
                        effect,
                        actor=actor_view,
                        payload=payload,
                        context=eval_context,
                    )
                )
        except (ValueError, ExpressionError) as exc:
            return self._finish_attempt(
                actor_id=actor_id,
                action_id=action_id,
                payload=payload,
                tx_id=tx_id,
                seq_start=seq_start,
                outcome=StepOutcome.UNSUPPORTED_SEMANTICS,
                reason_code="effect_error",
                failure_id="unsupported_semantics",
                category="business_rule",
                reason=str(exc),
                mutate=False,
            )

        redacted_payload = redact_payload(payload)
        staged_events: list[Event] = []
        event_types = list(branch.events) or ["action.committed"]
        next_seq = self._sequence
        next_clock = self._clock + 1
        for event_type in event_types:
            next_seq += 1
            staged_events.append(
                Event(
                    id=f"evt-{next_seq}",
                    type=event_type,
                    sequence=next_seq,
                    clock=next_clock,
                    actor_id=actor_id,
                    action_id=action_id,
                    branch_id=branch.id,
                    payload=copy.deepcopy(redacted_payload),
                    writes=copy.deepcopy(write_map) if event_type == event_types[0] else {},
                    outcome=StepOutcome.SUCCESS.value,
                    reason_code="committed",
                    transaction_id=tx_id,
                )
            )

        # --- external intents (stage only; execute at commit boundary) ---
        intent_names = list(branch.side_effect_intents) or list(action.external_side_effects)
        staged_intents: list[SideEffectIntent] = []
        for idx, kind in enumerate(intent_names):
            intent_payload = {
                "action_id": action_id,
                "actor_id": actor_id,
                "transaction_id": tx_id,
            }
            effect_digest = canonical_effect_payload_digest(
                kind=kind,
                target=None,
                payload=intent_payload,
            )
            intent_id = make_intent_id(
                run_id=run_id,
                transition_index=transition_index,
                actor_id=actor_id,
                action_id=action_id,
                effect_index=idx,
                canonical_effect_payload_digest=effect_digest,
            )
            staged_intents.append(
                SideEffectIntent(
                    id=intent_id,
                    kind=kind,
                    target=None,
                    payload=intent_payload,
                    executed=False,
                    recorded_only=True,
                )
            )

        # --- live external execution (optional, requires executor) ---
        receipts: list[SideEffectResult] = []
        if staged_intents and self._live_external_effects:
            assert self._external_executor is not None
            for effect_idx, intent in enumerate(staged_intents):
                receipt = self._external_executor.execute(intent, idempotency_key=intent.id)
                receipts.append(receipt)
                intent.receipt = receipt.model_dump(mode="json")
                if receipt.status == "executed":
                    intent.executed = True
                    intent.recorded_only = False
                elif receipt.status == "recorded":
                    intent.recorded_only = True
                    intent.executed = False
                else:
                    # Failed live effects must not disappear: persist intents + results.
                    for skipped in staged_intents[effect_idx + 1 :]:
                        skip_receipt = SideEffectResult(
                            intent_id=skipped.id,
                            intent_digest=canonical_hash(
                                {
                                    "id": skipped.id,
                                    "kind": skipped.kind,
                                    "target": skipped.target,
                                    "payload": skipped.payload,
                                }
                            ),
                            executor_id=self._external_executor.executor_id,
                            executor_version=self._external_executor.executor_version,
                            attempt=1,
                            idempotency_key=skipped.id,
                            started_at=receipt.started_at,
                            finished_at=receipt.finished_at,
                            status="skipped",
                            error="skipped after prior external effect failure",
                        )
                        skipped.receipt = skip_receipt.model_dump(mode="json")
                        receipts.append(skip_receipt)
                    self._recorded_intents.extend(staged_intents)
                    self._effect_receipts.extend(receipts)
                    return self._finish_attempt(
                        actor_id=actor_id,
                        action_id=action_id,
                        payload=payload,
                        tx_id=tx_id,
                        seq_start=seq_start,
                        transition_index=transition_index,
                        outcome=StepOutcome.EXTERNAL_FAILURE,
                        reason_code="external_effect_failed",
                        failure_id="external_failure",
                        category="dependency",
                        reason=receipt.error or f"external effect {intent.kind!r} failed",
                        mutate=False,
                        audit_event_type="action.external_failure",
                        side_effect_intents=staged_intents,
                        branch_id=branch.id,
                        allowed=True,
                    )
        else:
            for intent in staged_intents:
                receipt = recorded_receipt(intent)
                receipts.append(receipt)
                intent.receipt = receipt.model_dump(mode="json")
                intent.recorded_only = True
                intent.executed = False

        # --- atomic commit: events first, then apply event-derived writes ---
        self._clock = next_clock
        committed_events: list[Event] = []
        for event in staged_events:
            self._sequence = event.sequence
            self._event_log.append(event)
            self._link_audit(event)
            committed_events.append(event)
            # Authoritative state changes only via committed event effects.
            for key, value in event.writes.items():
                self._authoritative_state[key] = copy.deepcopy(value)

        for intent in staged_intents:
            self._recorded_intents.append(intent)
        self._effect_receipts.extend(receipts)

        self._task_state["steps"] = int(self._task_state.get("steps", 0)) + 1
        horizon = self._task_state.get("horizon")
        truncated = False
        terminal = bool(branch.terminal)
        outcome = StepOutcome.SUCCESS
        reason_code = "committed"
        if isinstance(horizon, int) and self._task_state["steps"] >= horizon:
            truncated = True
            terminal = True
            outcome = StepOutcome.TRUNCATED
            reason_code = "truncated"
        if self._goal_reached():
            terminal = True
        self._apply_terminal(
            terminal=terminal,
            truncated=truncated,
            reason_code=reason_code,
        )
        self._refresh_fingerprint()

        evidence = [
            {"kind": e, "action_id": action_id, "sequence": self._sequence}
            for e in (rule.emitted_evidence or action.evidence_emitted)
        ]
        self._record_decision(
            TransitionDecision(
                transaction_id=tx_id,
                actor_id=actor_id,
                action_id=action_id,
                outcome=outcome.value,
                reason_code=reason_code,
                branch_id=branch.id,
                allowed=True,
                transition_index=transition_index,
                payload_digest=payload_digest(redacted_payload),
                auth_digest=canonical_hash(
                    {
                        "action_id": action_id,
                        "actor_id": actor_id,
                        "authorization": action.authorization,
                    }
                ),
            )
        )
        tx_receipt = TransactionReceipt(
            transaction_id=tx_id,
            sequence_start=seq_start,
            sequence_end=self._sequence,
            outcome=outcome,
            reason_code=reason_code,
            mutated_authoritative_state=True,
            event_ids=[e.id for e in committed_events],
            intent_ids=[i.id for i in staged_intents],
            audit_head=self._audit_head,
            state_digest=self._digests()["state"],
        )
        self._pending_transactions.append(tx_receipt.model_dump(mode="json"))

        return StepResult(
            outcome=outcome,
            events=committed_events,
            side_effect_intents=staged_intents,
            observation=self.observe(actor_id),
            evidence=evidence,
            terminal=terminal,
            truncated=truncated,
            reason_code=tx_receipt.reason_code,
            info={
                "rule_id": rule.id,
                "branch_id": branch.id,
                "determinism": self._world.determinism,
                "reason_code": tx_receipt.reason_code,
                "transaction_id": tx_id,
                "transition_index": transition_index,
            },
            state_digest=tx_receipt.state_digest,
            transaction=tx_receipt,
        )

    def state(self) -> dict[str, Any]:
        self._ensure_initialized()
        self._check_strict_integrity()
        return copy.deepcopy(self._authoritative_state)

    def observe(self, actor_id: str) -> dict[str, Any]:
        """Return the actor's observation projection (fail-closed; never full-state leak)."""
        self._ensure_initialized()
        self._check_strict_integrity()
        actor = self._actors_ir.get(actor_id)
        if actor is None:
            raise KeyError(f"unknown actor {actor_id!r}")
        proj_id = actor.observation_projection_id
        if not proj_id:
            # No projection bound ⇒ empty observation (never authoritative state).
            return {}
        compiled = self._compiled_observations.get(proj_id)
        if compiled is None:
            # Unknown or unsupported projection ⇒ empty (fail closed).
            return {}
        actor_view = self._actor_runtime.get(actor_id, {})
        try:
            return project_state(
                self._authoritative_state,
                compiled,
                actor=actor,
                actor_view=actor_view,
                auth_context=self._auth_context,
            )
        except ObservationError:
            # Path errors / access failures ⇒ empty observation, never leak.
            return {}

    def snapshot(self) -> Snapshot:
        self._ensure_initialized()
        self._check_strict_integrity()
        digests = self._digests()
        snap = Snapshot(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            environment_id=self._world.environment_id,
            world_digest=self._world_digest,
            ir_version=self._world.ir_version or IR_VERSION,
            runtime_version=RUNTIME_VERSION,
            policy_digest=self._policy_digest,
            config_digest=self._config_digest,
            sequence=self._sequence,
            authoritative_state=copy.deepcopy(self._authoritative_state),
            initial_state_at_reset=copy.deepcopy(self._initial_state_at_reset),
            actors=copy.deepcopy(self._actor_runtime),
            scheduled_events=copy.deepcopy(self._scheduled_events),
            stubs=copy.deepcopy(self._stubs),
            clock=self._clock,
            rng=self._serialize_rng(),
            audit_head=self._audit_head,
            event_head=self._event_head,
            digests=digests,
            task_state=copy.deepcopy(self._task_state),
            pending_transactions=copy.deepcopy(self._pending_transactions),
            event_log=copy.deepcopy(self._event_log),
            recorded_intents=copy.deepcopy(self._recorded_intents),
            side_effect_results=copy.deepcopy(self._effect_receipts),
            seed=self._seed,
            episode_id=self._episode_id,
            terminal_record=self._terminal_record.model_copy(deep=True)
            if self._terminal_record is not None
            else None,
            terminal=self._terminal,
            truncated=self._truncated,
        )
        snap.snapshot_digest = self._snapshot_digest(snap)
        return snap

    def restore(self, snapshot: Snapshot) -> None:
        if snapshot.environment_id != self._world.environment_id:
            raise RuntimeError_(
                f"snapshot environment_id {snapshot.environment_id!r} does not match "
                f"{self._world.environment_id!r}"
            )
        if (
            snapshot.schema_version
            and snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION
            and snapshot.schema_version not in {SNAPSHOT_SCHEMA_VERSION, "1", ""}
        ):
            raise RuntimeError_(
                f"incompatible snapshot schema_version {snapshot.schema_version!r}; "
                f"expected {SNAPSHOT_SCHEMA_VERSION!r}"
            )
        if snapshot.world_digest and snapshot.world_digest != self._world_digest:
            raise RuntimeError_(
                f"snapshot world_digest mismatch: snapshot={snapshot.world_digest!r} "
                f"runtime={self._world_digest!r}"
            )
        if snapshot.ir_version and snapshot.ir_version != (self._world.ir_version or IR_VERSION):
            raise RuntimeError_(
                f"snapshot ir_version {snapshot.ir_version!r} incompatible with "
                f"{self._world.ir_version!r}"
            )
        if snapshot.runtime_version and snapshot.runtime_version != RUNTIME_VERSION:
            # Soft-bind: same major runtime family only (0.x → 0.x).
            snap_major = snapshot.runtime_version.split(".", 1)[0]
            run_major = RUNTIME_VERSION.split(".", 1)[0]
            if snap_major != run_major:
                raise RuntimeError_(
                    f"snapshot runtime_version {snapshot.runtime_version!r} incompatible "
                    f"with {RUNTIME_VERSION!r}"
                )
        if snapshot.snapshot_digest:
            expected = self._snapshot_digest(snapshot)
            if snapshot.snapshot_digest != expected:
                raise RuntimeError_("snapshot digest validation failed (tamper or corruption)")
        if snapshot.digests:
            state_digest = canonical_hash(snapshot.authoritative_state)
            if snapshot.digests.get("state") and snapshot.digests["state"] != state_digest:
                raise RuntimeError_("snapshot state digest mismatch")

        validate_event_log(snapshot.event_log)

        if snapshot.initial_state_at_reset:
            initial_at_reset = copy.deepcopy(snapshot.initial_state_at_reset)
        elif not snapshot.event_log:
            initial_at_reset = copy.deepcopy(snapshot.authoritative_state)
        else:
            raise RuntimeError_(
                "snapshot missing initial_state_at_reset required to reconstruct "
                "authoritative state from a non-empty event log; re-snapshot with "
                "the current runtime"
            )

        reconstructed = reconstruct_state(initial_at_reset, snapshot.event_log)
        if reconstructed != snapshot.authoritative_state:
            raise RuntimeError_(
                "snapshot authoritative_state diverges from event-log reconstruction"
            )
        if snapshot.digests.get("state"):
            reconstruct_digest = canonical_hash(reconstructed)
            if reconstruct_digest != snapshot.digests["state"]:
                raise RuntimeError_(
                    "reconstructed state digest does not match snapshot digests['state']"
                )

        self._authoritative_state = copy.deepcopy(snapshot.authoritative_state)
        self._initial_state_at_reset = initial_at_reset
        self._actor_runtime = copy.deepcopy(snapshot.actors)
        self._scheduled_events = copy.deepcopy(snapshot.scheduled_events)
        self._stubs = copy.deepcopy(snapshot.stubs)
        self._clock = snapshot.clock
        self._sequence = snapshot.sequence
        self._audit_head = snapshot.audit_head
        self._event_head = snapshot.event_head or snapshot.audit_head
        self._task_state = copy.deepcopy(snapshot.task_state)
        self._pending_transactions = copy.deepcopy(snapshot.pending_transactions)
        self._event_log = copy.deepcopy(snapshot.event_log)
        self._recorded_intents = copy.deepcopy(snapshot.recorded_intents)
        self._effect_receipts = copy.deepcopy(snapshot.side_effect_results)
        self._seed = snapshot.seed
        self._episode_id = snapshot.episode_id
        self._restore_rng(snapshot.rng)
        if snapshot.terminal_record is not None:
            self._terminal_record = snapshot.terminal_record.model_copy(deep=True)
            self._terminal = self._terminal_record.terminal
            self._truncated = self._terminal_record.truncated
        else:
            self._terminal = bool(snapshot.terminal or self._task_state.get("terminal", False))
            self._truncated = bool(snapshot.truncated or self._task_state.get("truncated", False))
            self._terminal_record = None
            if self._terminal or self._truncated:
                self._terminal_record = TerminalRecord(
                    terminal=self._terminal,
                    truncated=self._truncated,
                    reason_code="restored",
                    sequence=self._sequence,
                    clock=self._clock,
                    goal_reached=False,
                    task_id=self._task_state.get("task_id")
                    if isinstance(self._task_state.get("task_id"), str)
                    else None,
                )
        self._task_state["terminal"] = self._terminal
        self._task_state["truncated"] = self._truncated
        self._initialized = True
        self._refresh_fingerprint()

    def state_from_events(self) -> dict[str, Any]:
        """Reconstruct authoritative state by folding committed event writes."""
        self._ensure_initialized()
        return reconstruct_state(self._initial_state_at_reset, self._event_log)

    def fork(self) -> EventSourcedEnvironment:
        snap = self.snapshot()
        child = EventSourcedEnvironment(
            self._world,
            strict=self._strict,
            live_external_effects=self._live_external_effects,
            default_actor_id=self._default_actor_id,
            external_executor=self._external_executor,
            auth_context=self._auth_context,
        )
        child.restore(snap)
        child._initial_state_at_reset = copy.deepcopy(self._initial_state_at_reset)
        child._transition_decisions = copy.deepcopy(self._transition_decisions)
        return child

    def mutate_state(self, updates: dict[str, Any]) -> None:
        """Out-of-band mutation — forbidden in strict mode; non-authoritative otherwise."""
        if self._strict:
            raise StrictMutationError(
                "strict mode forbids out-of-band state mutation; use step() or restore()"
            )
        self._ensure_initialized()
        # Non-strict mutate_state is explicitly non-authoritative for release profiles:
        # it updates working state but does not emit events or advance the audit chain.
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
        payload: dict[str, Any],
        tx_id: str,
        seq_start: int,
    ) -> StepResult | None:
        auth = action.authorization
        if not auth:
            return None
        result = evaluate_authorization(
            auth,
            actor=actor,
            actor_view=actor_view,
            context={**self._auth_context, "payload": payload, "clock": self._clock},
        )
        if result.decision == AuthDecision.ALLOW:
            return None
        failure_id = action.failure_ids[0] if action.failure_ids else "unauthorized"
        category = "authorization"
        if failure_id in self._failures:
            category = self._failures[failure_id].category
        if result.decision == AuthDecision.INDETERMINATE:
            outcome = StepOutcome.INDETERMINATE
            reason_code = result.reason_code
        else:
            outcome = StepOutcome.DENIED
            reason_code = result.reason_code
        return self._finish_attempt(
            actor_id=actor.id,
            action_id=action.id,
            payload=payload,
            tx_id=tx_id,
            seq_start=seq_start,
            outcome=outcome,
            reason_code=reason_code,
            failure_id=failure_id,
            category=category,
            reason=result.reason,
            mutate=False,
            audit_event_type="action.denied",
        )

    def _check_preconditions(
        self,
        action: ActionContract,
        actor_view: dict[str, Any],
        payload: dict[str, Any],
        tx_id: str,
        seq_start: int,
    ) -> StepResult | None:
        for constraint in action.preconditions:
            try:
                ok = evaluate_constraint(
                    constraint,
                    state=self._authoritative_state,
                    actor=actor_view,
                    payload=payload,
                    context={**self._auth_context, "clock": self._clock},
                )
            except ExpressionError as exc:
                return self._finish_attempt(
                    actor_id=str(actor_view.get("id")),
                    action_id=action.id,
                    payload=payload,
                    tx_id=tx_id,
                    seq_start=seq_start,
                    outcome=StepOutcome.UNSUPPORTED_SEMANTICS,
                    reason_code="unsupported_precondition",
                    failure_id="unsupported_semantics",
                    category="business_rule",
                    reason=str(exc),
                    mutate=False,
                )
            if not ok:
                return self._finish_attempt(
                    actor_id=str(actor_view.get("id")),
                    action_id=action.id,
                    payload=payload,
                    tx_id=tx_id,
                    seq_start=seq_start,
                    outcome=StepOutcome.PRECONDITION_FAILED,
                    reason_code="precondition_failed",
                    failure_id="precondition_failed",
                    category="business_rule",
                    reason=f"precondition failed: {constraint.expression}",
                    mutate=False,
                )
        return None

    def _select_transition(
        self,
        action_id: str,
        actor_view: dict[str, Any],
        payload: dict[str, Any],
    ) -> TransitionRule | None:
        for rule in self._transitions_by_action.get(action_id, []):
            if rule.guard is None:
                return rule
            if evaluate_constraint(
                rule.guard,
                state=self._authoritative_state,
                actor=actor_view,
                payload=payload,
                context={**self._auth_context, "clock": self._clock},
            ):
                return rule
        return None

    def _select_branch(self, rule: TransitionRule) -> TransitionBranch | None:
        if not rule.branches:
            return None
        if rule.kind == "deterministic" or self._world.determinism == "fully_deterministic":
            return rule.branches[0]
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
                try:
                    if not evaluate_constraint(
                        claim,
                        state=self._authoritative_state,
                        actor={},
                    ):
                        return False
                except ExpressionError:
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
            "event_head": self._event_head or canonical_hash(""),
            "events": canonical_hash([e.model_dump(mode="json") for e in self._event_log]),
            "world": self._world_digest,
            "policy": self._policy_digest,
            "config": self._config_digest,
        }

    def _snapshot_digest(self, snap: Snapshot) -> str:
        payload = snap.model_dump(mode="json")
        payload.pop("snapshot_digest", None)
        return canonical_hash(payload)

    def _link_audit(self, event: Event) -> None:
        self._audit_head = canonical_hash(
            {
                "prev": self._audit_head,
                "event": event.model_dump(mode="json"),
            }
        )
        self._event_head = canonical_hash(
            {
                "prev": self._event_head,
                "event_id": event.id,
                "sequence": event.sequence,
                "type": event.type,
            }
        )

    def _apply_terminal(
        self,
        *,
        terminal: bool,
        truncated: bool,
        reason_code: str,
    ) -> None:
        self._terminal = terminal
        self._truncated = truncated
        self._task_state["terminal"] = terminal
        self._task_state["truncated"] = truncated
        if terminal or truncated:
            task_id = self._task_state.get("task_id")
            self._terminal_record = TerminalRecord(
                terminal=terminal,
                truncated=truncated,
                reason_code=reason_code,
                sequence=self._sequence,
                clock=self._clock,
                goal_reached=self._goal_reached() if terminal else False,
                task_id=task_id if isinstance(task_id, str) else None,
            )
        else:
            self._terminal_record = None

    def _record_decision(self, decision: TransitionDecision) -> None:
        self._transition_decisions.append(decision)

    def _finish_attempt(
        self,
        *,
        actor_id: str,
        action_id: str,
        payload: dict[str, Any],
        tx_id: str,
        seq_start: int,
        outcome: StepOutcome,
        reason_code: str,
        failure_id: str,
        category: str,
        reason: str,
        mutate: bool,
        audit_event_type: str = "action.rejected",
        transition_index: int | None = None,
        side_effect_intents: list[SideEffectIntent] | None = None,
        branch_id: str | None = None,
        allowed: bool = False,
    ) -> StepResult:
        """Emit audit/transaction accounting for a non-commit (or terminal) attempt."""
        del mutate  # authoritative state never mutates on rejection paths
        idx = seq_start if transition_index is None else transition_index
        intents = list(side_effect_intents or [])
        self._clock += 1
        self._sequence += 1
        redacted = redact_payload(payload)
        event = Event(
            id=f"evt-{self._sequence}",
            type=audit_event_type,
            sequence=self._sequence,
            clock=self._clock,
            actor_id=actor_id,
            action_id=action_id,
            branch_id=branch_id,
            payload=redacted,
            writes={},
            outcome=outcome.value,
            reason_code=reason_code,
            transaction_id=tx_id,
        )
        self._event_log.append(event)
        self._link_audit(event)
        self._record_decision(
            TransitionDecision(
                transaction_id=tx_id,
                actor_id=actor_id,
                action_id=action_id,
                outcome=outcome.value,
                reason_code=reason_code,
                branch_id=branch_id,
                allowed=allowed,
                transition_index=idx,
                payload_digest=payload_digest(redacted),
                auth_digest="",
            )
        )
        receipt = TransactionReceipt(
            transaction_id=tx_id,
            sequence_start=seq_start,
            sequence_end=self._sequence,
            outcome=outcome,
            reason_code=reason_code,
            mutated_authoritative_state=False,
            event_ids=[event.id],
            intent_ids=[i.id for i in intents],
            audit_head=self._audit_head,
            state_digest=self._digests()["state"],
        )
        self._pending_transactions.append(receipt.model_dump(mode="json"))

        observation: dict[str, Any] = {}
        if actor_id in self._actors_ir and self._initialized:
            observation = self.observe(actor_id)
        return StepResult(
            outcome=outcome,
            events=[event],
            side_effect_intents=intents,
            observation=observation,
            failure_id=failure_id,
            failure_category=category,
            reason_code=reason_code,
            info={
                "reason": reason,
                "action_id": action_id,
                "actor_id": actor_id,
                "reason_code": reason_code,
                "transaction_id": tx_id,
                "transition_index": idx,
            },
            terminal=outcome == StepOutcome.TERMINAL or self._terminal,
            truncated=False,
            state_digest=receipt.state_digest,
            transaction=receipt,
        )
