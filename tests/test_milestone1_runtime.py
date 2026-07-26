"""Milestone 1 runtime correctness tests (EAC-R01-R07)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from envassure.api import World
from envassure.expressions import (
    EvalContext,
    ExpressionError,
    evaluate,
    evaluate_bool,
    parse_expression,
    parse_structured,
    validate_expression,
)
from envassure.expressions.parser import parse_effect
from envassure.ir.models import ActorDefinition, TransitionBranch
from envassure.runtime import (
    EventSourcedEnvironment,
    RuntimeError_,
    StepOutcome,
)
from envassure.runtime.authorization import (
    AuthDecision,
    actor_discharges,
    evaluate_authorization,
)
from envassure.runtime.events import SideEffectIntent
from envassure.runtime.external import EffectReceipt, intent_digest
from envassure.runtime.payloads import PayloadValidationError, redact_payload, validate_payload
from envassure.runtime.snapshot import Snapshot


def _counter_world():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("ex_counter_m1", root)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_counter_world()


# --- R01 outcomes -----------------------------------------------------------


def test_step_outcome_success_and_denied() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    ok = env.step("client", "increment")
    assert ok.outcome == StepOutcome.SUCCESS
    assert ok.ok is True
    assert ok.reason_code == "committed"
    assert ok.status == "success"

    denied = env.step("client", "reset")
    assert denied.outcome == StepOutcome.DENIED
    assert denied.ok is False
    assert denied.reason_code == "authorization_denied"
    assert denied.failure_category == "authorization"


def test_terminal_outcome_when_episode_ended() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0, options={"task_id": "reach_three"})
    for _ in range(3):
        env.step("client", "increment")
    assert env.snapshot().terminal is True
    again = env.step("client", "increment")
    assert again.outcome == StepOutcome.TERMINAL
    assert again.ok is False


# --- R02 payloads -----------------------------------------------------------


def test_payload_schema_validation_and_redaction() -> None:
    w = World("pay.v1", "Payload")
    w.state("n", initial_generator="0")
    w.actor("a", available_actions=["set"])
    w.action(
        "set",
        actor_classes=["a"],
        intended_effects=["n = payload.value"],
        success_outcomes=["ok"],
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer"}, "token": {"type": "string"}},
            "additionalProperties": False,
        },
    )
    w.transition(
        "t_set",
        action_id="set",
        branches=[TransitionBranch(id="t_set.ok", events=["set"])],
    )
    world = w.compile()

    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    bad = env.step("a", "set", {"value": "x"})
    assert bad.outcome == StepOutcome.INVALID_INPUT
    assert bad.events  # audit event emitted

    good = env.step("a", "set", {"value": 7, "token": "secret-token"})
    assert good.outcome == StepOutcome.SUCCESS
    assert env.state()["n"] == 7
    assert good.events[0].payload["token"] == "***REDACTED***"


def test_validate_payload_property_malformed() -> None:
    schema = {
        "type": "object",
        "required": ["n"],
        "properties": {"n": {"type": "integer", "minimum": 0}},
        "additionalProperties": False,
    }
    validate_payload(schema, {"n": 1})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": -1})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 1, "extra": True})


@given(st.dictionaries(st.sampled_from(["password", "token", "ok"]), st.text(max_size=8)))
@settings(max_examples=25)
def test_redact_payload_property(data: dict[str, str]) -> None:
    redacted = redact_payload(data)
    for key, value in redacted.items():
        if key.lower() in {"password", "token"}:
            assert value == "***REDACTED***"
        else:
            assert value == data[key]


# --- R03 expressions --------------------------------------------------------


def test_expression_ast_paths_and_payload() -> None:
    expr = parse_expression("state.count + payload.delta")
    ctx = EvalContext(state={"count": 2}, payload={"delta": 3})
    assert evaluate(expr, ctx) == 5
    assert evaluate_bool(parse_expression("count == 2"), ctx) is True
    assert evaluate_bool(
        parse_expression('actor.roles contains "admin"'), EvalContext(actor={"roles": ["admin"]})
    )


def test_expression_fail_closed_unsupported() -> None:
    expr, diags = validate_expression("evil_fn(1)")
    assert expr is None
    assert diags
    with pytest.raises(ExpressionError):
        parse_expression("@@@")


def test_structured_and_effect_parse() -> None:
    expr = parse_structured({"eq": ["state.count", 0]})
    assert evaluate_bool(expr, EvalContext(state={"count": 0})) is True
    name, op, rhs = parse_effect("count += payload.n")
    assert name == "count" and op == "+="
    assert evaluate(rhs, EvalContext(payload={"n": 4})) == 4


def test_collection_predicate_bounded() -> None:
    expr = parse_expression("all x in state.items: x > 0")
    assert evaluate_bool(expr, EvalContext(state={"items": [1, 2, 3]})) is True
    assert evaluate_bool(expr, EvalContext(state={"items": [1, -1]})) is False


# --- R04 authorization ------------------------------------------------------


def test_auth_fail_closed_unknown_and_role() -> None:
    actor = ActorDefinition(id="u", actor_class="u", roles=["reader"])
    denied = evaluate_authorization("role:admin", actor=actor, actor_view={"roles": ["reader"]})
    assert denied.decision == AuthDecision.DENY

    indeterminate = evaluate_authorization(
        "magic:portal",
        actor=actor,
        actor_view={"roles": ["reader"]},
    )
    assert indeterminate.decision == AuthDecision.INDETERMINATE
    assert indeterminate.reason_code == "indeterminate_unsupported_authorization"


def test_auth_tenant_revocation_expiry_scope() -> None:
    actor = ActorDefinition(
        id="u",
        actor_class="u",
        roles=["ops"],
        credentials=["tenant:acme"],
        revocation_rules=["role:ops"],
    )
    assert actor_discharges("role:ops", actor) is False

    tenant_actor = ActorDefinition(id="t", actor_class="t", credentials=["tenant:acme"])
    ok = evaluate_authorization(
        "tenant:acme",
        actor=tenant_actor,
        actor_view={"tenant": "acme"},
    )
    assert ok.decision == AuthDecision.ALLOW
    bad_tenant = evaluate_authorization(
        "tenant:other",
        actor=tenant_actor,
        actor_view={"tenant": "acme"},
    )
    assert bad_tenant.decision == AuthDecision.DENY

    now = datetime(2026, 6, 1, tzinfo=UTC).isoformat()
    expired = evaluate_authorization(
        "temporal:expires:2026-01-01T00:00:00+00:00",
        actor=tenant_actor,
        actor_view={},
        context={"now": now},
    )
    assert expired.decision == AuthDecision.DENY
    assert expired.reason_code == "authorization_expired"

    scope_ok = evaluate_authorization(
        "scope:orders.write",
        actor=tenant_actor,
        actor_view={"scope": "orders"},
    )
    assert scope_ok.decision == AuthDecision.ALLOW
    expansion = evaluate_authorization(
        "scope:orders",
        actor=tenant_actor,
        actor_view={"scope": "orders.write"},
    )
    assert expansion.decision == AuthDecision.DENY
    assert expansion.reason_code == "authorization_scope_expansion"


def test_runtime_unsupported_auth_is_indeterminate_not_allow() -> None:
    w = World("auth.v1", "Auth")
    w.state("x", initial_generator="0")
    w.actor("a", available_actions=["ping"])
    w.action(
        "ping",
        actor_classes=["a"],
        authorization="unknown_scheme:xyz",
        intended_effects=["x += 1"],
        success_outcomes=["ok"],
    )
    w.transition(
        "t",
        action_id="ping",
        branches=[TransitionBranch(id="t.ok", events=["pinged"])],
    )
    world = w.compile()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    result = env.step("a", "ping")
    assert result.outcome == StepOutcome.INDETERMINATE
    assert result.ok is False
    assert env.state()["x"] == 0
    assert len(result.events) >= 1


# --- R05 event sourcing -----------------------------------------------------


def test_every_attempt_emits_transaction_and_audit_event() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    denied = env.step("client", "reset")
    assert denied.transaction is not None
    assert denied.transaction.mutated_authoritative_state is False
    assert len(denied.events) >= 1
    assert env.state()["count"] == 0

    ok = env.step("client", "increment")
    assert ok.transaction is not None
    assert ok.transaction.mutated_authoritative_state is True
    assert env.snapshot().sequence == denied.transaction.sequence_end + len(ok.events)


def test_denied_does_not_mutate_authoritative_state() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    env.step("client", "increment")
    before = env.state()["count"]
    audit_before = len(env.snapshot().event_log)
    denied = env.step("client", "reset")
    assert not denied.ok
    assert env.state()["count"] == before
    assert len(env.snapshot().event_log) == audit_before + 1


def test_empty_branch_events_still_commit_via_default_event() -> None:
    w = World("empty.v1", "EmptyEvents")
    w.state("x", initial_generator="0")
    w.actor("a", available_actions=["bump"])
    w.action(
        "bump",
        actor_classes=["a"],
        intended_effects=["x += 1"],
        success_outcomes=["ok"],
    )
    w.transition(
        "t",
        action_id="bump",
        branches=[TransitionBranch(id="t.ok", events=[])],
    )
    world = w.compile()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    result = env.step("a", "bump")
    assert result.ok
    assert result.events[0].type == "action.committed"
    assert env.state()["x"] == 1
    assert result.side_effect_intents == []


# --- R06 external effects ---------------------------------------------------


class _OkExecutor:
    executor_id = "test-exec"
    executor_version = "1.0"

    def execute(
        self,
        intent: SideEffectIntent,
        *,
        attempt: int = 1,
        idempotency_key: str | None = None,
    ) -> EffectReceipt:
        from datetime import datetime

        now = datetime.now(UTC).isoformat()
        return EffectReceipt(
            intent_id=intent.id,
            intent_digest=intent_digest(intent),
            executor_id=self.executor_id,
            executor_version=self.executor_version,
            attempt=attempt,
            idempotency_key=idempotency_key or intent.id,
            started_at=now,
            finished_at=now,
            status="executed",
            response_digest="ok",
        )


def test_live_effects_require_executor() -> None:
    world = _counter_world()
    with pytest.raises(RuntimeError_, match="ExternalEffectExecutor"):
        EventSourcedEnvironment(world, live_external_effects=True)


def test_live_effects_with_executor_receipt() -> None:
    w = World("fx.v1", "FX")
    w.state("x", initial_generator="0")
    w.actor("a", available_actions=["ping"])
    w.action(
        "ping",
        actor_classes=["a"],
        intended_effects=["x += 1"],
        external_side_effects=["http.notify"],
        success_outcomes=["ok"],
    )
    w.transition(
        "t_ping",
        action_id="ping",
        branches=[
            TransitionBranch(
                id="t_ping.ok",
                events=["pinged"],
                side_effect_intents=["http.notify"],
            )
        ],
    )
    world = w.compile()
    env = EventSourcedEnvironment(
        world,
        live_external_effects=True,
        external_executor=_OkExecutor(),
    )
    env.reset(seed=0)
    result = env.step("a", "ping")
    assert result.ok
    intent = result.side_effect_intents[0]
    assert intent.executed is True
    assert intent.recorded_only is False
    assert intent.receipt is not None
    assert intent.receipt["status"] == "executed"
    assert intent.receipt["executor_id"] == "test-exec"


# --- R07 snapshot v2 --------------------------------------------------------


def test_snapshot_v2_terminality_and_digests() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=1, options={"task_id": "reach_three"})
    env.step("client", "increment")
    env.step("client", "increment")
    env.step("client", "increment")
    snap = env.snapshot()
    assert snap.schema_version == "2"
    assert snap.terminal is True
    assert snap.world_digest
    assert snap.snapshot_digest
    assert snap.ir_version
    assert snap.runtime_version
    assert "state" in snap.digests
    assert snap.event_head

    env2 = EventSourcedEnvironment(world)
    env2.reset(seed=99)
    env2.restore(snap)
    assert env2.state()["count"] == 3
    assert env2.snapshot().terminal is True
    assert env2.snapshot().digests["state"] == snap.digests["state"]


def test_snapshot_rejects_world_mismatch_and_tamper() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    env.step("client", "increment")
    snap = env.snapshot()

    other = World("other.v1", "Other")
    other.state("count", initial_generator="0")
    other.actor("client", available_actions=["increment"])
    other.action(
        "increment",
        actor_classes=["client"],
        intended_effects=["count += 1"],
        success_outcomes=["ok"],
    )
    other.transition(
        "t",
        action_id="increment",
        branches=[TransitionBranch(id="t.ok", events=["inc"])],
    )
    other_world = other.compile()
    env_other = EventSourcedEnvironment(other_world)
    env_other.reset(seed=0)
    with pytest.raises(RuntimeError_, match="environment_id"):
        env_other.restore(snap)

    tampered = Snapshot.model_validate(
        {**snap.model_dump(mode="json"), "authoritative_state": {"count": 99}}
    )
    # Recompute would fail digest check when snapshot_digest present.
    with pytest.raises(RuntimeError_, match="digest"):
        env.restore(tampered)
