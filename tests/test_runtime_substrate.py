"""EAC-02 / EAC-03 runtime substrate regressions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from envassure.api import World
from envassure.ir.models import TransitionBranch
from envassure.runtime import (
    EventLogValidationError,
    EventSourcedEnvironment,
    SideEffectResult,
    StepOutcome,
    reconstruct_state,
    validate_event_log,
)
from envassure.runtime.events import Event, SideEffectIntent
from envassure.runtime.external import EffectReceipt, intent_digest
from envassure.runtime.intent_ids import (
    canonical_effect_payload_digest,
    make_intent_id,
    make_transaction_id,
)


def _counter_world():
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("ex_counter_substrate", root)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_counter_world()


def _multi_effect_world() -> object:
    w = World("fx.multi.v1", "FX Multi")
    w.state("x", initial_generator="0")
    w.actor("a", available_actions=["ping"])
    w.action(
        "ping",
        actor_classes=["a"],
        intended_effects=["x += 1"],
        external_side_effects=["http.notify", "http.audit"],
        success_outcomes=["ok"],
    )
    w.transition(
        "t_ping",
        action_id="ping",
        branches=[
            TransitionBranch(
                id="t_ping.ok",
                events=["pinged"],
                side_effect_intents=["http.notify", "http.audit"],
            )
        ],
    )
    return w.compile()


class _FailingExecutor:
    executor_id = "fail-exec"
    executor_version = "1.0"

    def execute(
        self,
        intent: SideEffectIntent,
        *,
        attempt: int = 1,
        idempotency_key: str | None = None,
    ) -> SideEffectResult:
        now = datetime.now(UTC).isoformat()
        return SideEffectResult(
            intent_id=intent.id,
            intent_digest=intent_digest(intent),
            executor_id=self.executor_id,
            executor_version=self.executor_version,
            attempt=attempt,
            idempotency_key=idempotency_key or intent.id,
            started_at=now,
            finished_at=now,
            status="failed",
            error="simulated external failure",
        )


# --- EAC-02 reconstruction / audit trail ------------------------------------


def test_state_equals_fold_of_committed_events() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0, options={"episode_id": "run-reconstruct"})
    for _ in range(5):
        result = env.step("client", "increment")
        assert result.ok
    assert env.state() == env.state_from_events()
    snap = env.snapshot()
    assert env.state() == reconstruct_state({"count": 0}, snap.event_log)
    assert snap.initial_state_at_reset == {"count": 0}


def test_restore_enforces_reconstruct_digest_equality() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0, options={"episode_id": "run-restore-eq"})
    for _ in range(3):
        assert env.step("client", "increment").ok
    snap = env.snapshot()
    assert snap.initial_state_at_reset == {"count": 0}

    env2 = EventSourcedEnvironment(world)
    env2.reset(seed=99)
    env2.restore(snap)
    assert env2.state() == env2.state_from_events()
    assert env2.state() == {"count": 3}

    tampered = snap.model_copy(deep=True)
    tampered.authoritative_state = {"count": 99}
    # Keep digests consistent with tampered state so we hit reconstruct equality.
    from envassure.canonical import canonical_hash

    tampered.digests = dict(tampered.digests)
    tampered.digests["state"] = canonical_hash(tampered.authoritative_state)
    tampered.snapshot_digest = ""
    env3 = EventSourcedEnvironment(world)
    env3.reset(seed=0)
    with pytest.raises(RuntimeError, match="diverges from event-log reconstruction"):
        env3.restore(tampered)


def test_restore_rejects_legacy_snapshot_missing_initial_state() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0, options={"episode_id": "legacy-snap"})
    assert env.step("client", "increment").ok
    snap = env.snapshot()
    payload = snap.model_dump(mode="json")
    payload["initial_state_at_reset"] = {}
    payload["snapshot_digest"] = ""
    legacy = type(snap).model_validate(payload)
    env2 = EventSourcedEnvironment(world)
    env2.reset(seed=0)
    with pytest.raises(RuntimeError, match="missing initial_state_at_reset"):
        env2.restore(legacy)


def test_denied_path_reconstructable_without_state_writes() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    before = env.state()
    denied = env.step("client", "reset")
    assert denied.outcome == StepOutcome.DENIED
    assert denied.events
    assert all(not e.writes for e in denied.events)
    assert env.state() == before
    assert env.state_from_events() == before
    validate_event_log(env.snapshot().event_log)


def test_failed_external_effect_survives_snapshot_restore() -> None:
    world = _multi_effect_world()
    env = EventSourcedEnvironment(
        world,
        live_external_effects=True,
        external_executor=_FailingExecutor(),
    )
    env.reset(seed=0, options={"episode_id": "run-fail-fx"})
    result = env.step("a", "ping")
    assert result.outcome == StepOutcome.EXTERNAL_FAILURE
    assert len(result.side_effect_intents) == 2
    assert env.state()["x"] == 0
    snap = env.snapshot()
    assert len(snap.recorded_intents) == 2
    assert len(snap.side_effect_results) == 2
    assert snap.side_effect_results[0].status == "failed"
    assert snap.side_effect_results[1].status == "skipped"

    env2 = EventSourcedEnvironment(
        world,
        live_external_effects=True,
        external_executor=_FailingExecutor(),
    )
    env2.reset(seed=99)
    env2.restore(snap)
    assert len(env2.snapshot().recorded_intents) == 2
    assert len(env2.snapshot().side_effect_results) == 2
    assert env2.snapshot().side_effect_results[0].status == "failed"
    assert env2.state()["x"] == 0


def test_validate_event_log_rejects_gap_and_duplicate_id() -> None:
    events = [
        Event(id="evt-1", type="a", sequence=1, clock=1),
        Event(id="evt-3", type="a", sequence=3, clock=2),
    ]
    with pytest.raises(EventLogValidationError, match="sequence gap"):
        validate_event_log(events)

    dup = [
        Event(id="evt-1", type="a", sequence=1, clock=1),
        Event(id="evt-1", type="a", sequence=2, clock=2),
    ]
    with pytest.raises(EventLogValidationError, match="duplicate event id"):
        validate_event_log(dup)

    dup_seq = [
        Event(id="evt-1", type="a", sequence=1, clock=1),
        Event(id="evt-2", type="a", sequence=1, clock=2),
    ]
    with pytest.raises(EventLogValidationError, match="duplicate event sequence"):
        validate_event_log(dup_seq)

    non_mono = [
        Event(id="evt-1", type="a", sequence=1, clock=2),
        Event(id="evt-2", type="a", sequence=2, clock=1),
    ]
    with pytest.raises(EventLogValidationError, match="non-monotonic clock"):
        validate_event_log(non_mono)


def test_terminal_record_round_trips_in_snapshot() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=1, options={"task_id": "reach_three", "episode_id": "term-run"})
    for _ in range(3):
        env.step("client", "increment")
    snap = env.snapshot()
    assert snap.terminal_record is not None
    assert snap.terminal_record.terminal is True
    assert snap.terminal is True
    env2 = EventSourcedEnvironment(world)
    env2.reset(seed=0)
    env2.restore(snap)
    assert env2.snapshot().terminal_record is not None
    assert env2.snapshot().terminal_record.terminal is True
    assert env2.snapshot().terminal is True


def test_effect_receipt_alias_is_side_effect_result() -> None:
    assert EffectReceipt is SideEffectResult


# --- EAC-03 deterministic identifiers ---------------------------------------


def test_intent_id_idempotent_for_same_inputs() -> None:
    digest = canonical_effect_payload_digest(
        kind="http.notify",
        target=None,
        payload={"action_id": "ping", "actor_id": "a"},
    )
    kwargs = {
        "run_id": "run-1",
        "transition_index": 0,
        "actor_id": "a",
        "action_id": "ping",
        "effect_index": 0,
        "canonical_effect_payload_digest": digest,
    }
    assert make_intent_id(**kwargs) == make_intent_id(**kwargs)
    assert make_intent_id(**kwargs).startswith("sei-")
    assert len(make_intent_id(**kwargs)) == 4 + 32


def test_intent_id_distinct_for_effect_or_transition_index() -> None:
    digest = canonical_effect_payload_digest(
        kind="http.notify",
        target=None,
        payload={"action_id": "ping", "actor_id": "a"},
    )
    base = {
        "run_id": "run-1",
        "transition_index": 0,
        "actor_id": "a",
        "action_id": "ping",
        "effect_index": 0,
        "canonical_effect_payload_digest": digest,
    }
    a = make_intent_id(**base)
    b = make_intent_id(**{**base, "effect_index": 1})
    c = make_intent_id(**{**base, "transition_index": 1})
    assert a != b
    assert a != c
    assert b != c


def test_intent_ids_unique_within_multi_effect_run() -> None:
    world = _multi_effect_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0, options={"episode_id": "stable-run"})
    result = env.step("a", "ping")
    assert result.ok
    ids = [i.id for i in result.side_effect_intents]
    assert len(ids) == 2
    assert len(set(ids)) == 2
    assert all(i.startswith("sei-") for i in ids)

    # Idempotent retry of the same transition identity yields the same ids.
    env2 = EventSourcedEnvironment(world)
    env2.reset(seed=0, options={"episode_id": "stable-run"})
    again = env2.step("a", "ping")
    assert [i.id for i in again.side_effect_intents] == ids
    assert again.transaction is not None
    assert result.transaction is not None
    assert again.transaction.transaction_id == result.transaction.transaction_id


def test_transaction_id_stable_from_run_and_transition_index() -> None:
    a = make_transaction_id(run_id="run-1", transition_index=0)
    b = make_transaction_id(run_id="run-1", transition_index=0)
    c = make_transaction_id(run_id="run-1", transition_index=1)
    assert a == b
    assert a != c
    assert a.startswith("tx-")


def test_episode_id_seed_derived_when_omitted() -> None:
    world = _counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=7)
    snap = env.snapshot()
    assert snap.episode_id == "ep-seed-7"
    env.reset(seed=7, options={"episode_id": "custom-ep"})
    assert env.snapshot().episode_id == "custom-ep"


@given(
    st.integers(min_value=0, max_value=64),
    st.integers(min_value=0, max_value=8),
    st.integers(min_value=0, max_value=8),
)
@settings(max_examples=40)
def test_intent_id_property_deterministic_and_index_sensitive(
    transition_index: int,
    effect_a: int,
    effect_b: int,
) -> None:
    digest = canonical_effect_payload_digest(
        kind="http.notify",
        target=None,
        payload={"k": "v"},
    )
    base = {
        "run_id": "prop-run",
        "transition_index": transition_index,
        "actor_id": "a",
        "action_id": "ping",
        "canonical_effect_payload_digest": digest,
    }
    left = make_intent_id(**base, effect_index=effect_a)
    right = make_intent_id(**base, effect_index=effect_b)
    assert left == make_intent_id(**base, effect_index=effect_a)
    assert left.startswith("sei-")
    if effect_a != effect_b:
        assert left != right


@given(st.integers(min_value=1, max_value=4), st.integers(min_value=0, max_value=6))
@settings(max_examples=30)
def test_validate_event_log_property_contiguous_and_gap(
    start: int,
    length: int,
) -> None:
    events = [
        Event(id=f"evt-{start + i}", type="t", sequence=start + i, clock=start + i)
        for i in range(length)
    ]
    validate_event_log(events)
    if length >= 2:
        gapped = [
            events[0],
            Event(
                id="evt-gap",
                type="t",
                sequence=events[0].sequence + 2,
                clock=events[0].clock + 2,
            ),
        ]
        with pytest.raises(EventLogValidationError, match="sequence gap"):
            validate_event_log(gapped)
