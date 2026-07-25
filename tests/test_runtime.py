"""Phase 3 runtime tests (EAC-013-016)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from envassure.runtime import (
    EventSourcedEnvironment,
    StrictMutationError,
    generate_runtime_module,
)
from envassure.runtime.adapters.gymnasium_env import _GYM_IMPORT_ERROR, GymAssureEnv


def _load_counter_world() -> Any:
    root = Path(__file__).resolve().parents[1] / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("ex_counter_runtime", root)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_counter_world()


def test_reset_step_observe() -> None:
    world = _load_counter_world()
    env = EventSourcedEnvironment(world)
    obs = env.reset(seed=7)
    assert obs == {"count": 0}
    assert env.state()["count"] == 0

    result = env.step("client", "increment")
    assert result.ok
    assert result.events[0].type == "count.incremented"
    assert result.observation["count"] == 1
    assert env.state()["count"] == 1

    result2 = env.step("client", "get")
    assert result2.ok
    assert result2.observation["count"] == 1


def test_snapshot_restore_fork() -> None:
    world = _load_counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=1)
    env.step("client", "increment")
    env.step("client", "increment")
    snap = env.snapshot()
    assert snap.authoritative_state["count"] == 2
    assert snap.clock == 2
    assert "state" in snap.digests
    assert snap.audit_head

    env.step("client", "increment")
    assert env.state()["count"] == 3

    env.restore(snap)
    assert env.state()["count"] == 2
    assert env.snapshot().digests["state"] == snap.digests["state"]

    forked = env.fork()
    forked.step("client", "increment")
    assert forked.state()["count"] == 3
    assert env.state()["count"] == 2


def test_strict_mode_forbids_out_of_band_mutation() -> None:
    world = _load_counter_world()
    env = EventSourcedEnvironment(world, strict=True)
    env.reset(seed=0)
    with pytest.raises(StrictMutationError):
        env.mutate_state({"count": 99})
    # Returned state is a copy — mutating it must not affect the environment.
    view = env.state()
    view["count"] = 99
    assert env.state()["count"] == 0


def test_side_effect_intents_recorded_by_default() -> None:
    from envassure.api import World
    from envassure.ir.models import TransitionBranch

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
    env = EventSourcedEnvironment(world, live_external_effects=False)
    env.reset(seed=0)
    result = env.step("a", "ping")
    assert result.ok
    assert len(result.side_effect_intents) == 1
    intent = result.side_effect_intents[0]
    assert intent.kind == "http.notify"
    assert intent.recorded_only is True
    assert intent.executed is False


def test_authorization_rejects_reset_without_admin() -> None:
    world = _load_counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    env.step("client", "increment")
    denied = env.step("client", "reset")
    assert not denied.ok
    assert denied.failure_category == "authorization"


def test_deterministic_replay_property() -> None:
    world = _load_counter_world()
    actions = [("client", "increment"), ("client", "increment"), ("client", "get")]
    digests: list[str] = []
    states: list[dict[str, Any]] = []
    for _ in range(5):
        env = EventSourcedEnvironment(world)
        env.reset(seed=42)
        for actor_id, action_id in actions:
            assert env.step(actor_id, action_id).ok
        snap = env.snapshot()
        digests.append(snap.digests["state"])
        states.append(env.state())
    assert len(set(digests)) == 1
    assert all(s == states[0] for s in states)
    assert states[0]["count"] == 2


def test_codegen_applies_writes(tmp_path: Path) -> None:
    world = _load_counter_world()
    source = generate_runtime_module(world)
    assert "counter.v1" in source
    path = tmp_path / "generated_counter.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("gen_counter", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    state = mod.step_sequence(["increment", "increment", "increment"])
    assert state["count"] == 3


def test_gym_adapter_import_error_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.runtime.adapters.gymnasium_env as gym_mod

    def _missing() -> Any:
        raise ImportError(_GYM_IMPORT_ERROR)

    monkeypatch.setattr(gym_mod, "_import_gymnasium", _missing)
    world = _load_counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    with pytest.raises(ImportError, match=r"pip install envassure\[gym\]") as exc_info:
        GymAssureEnv(env, actor_id="client", action_ids=["increment", "get"])
    assert "envassure[gym]" in str(exc_info.value)


def test_protocol_runtime_checkable() -> None:
    from envassure.runtime.protocol import AssuredEnvironment

    world = _load_counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    assert isinstance(env, AssuredEnvironment)
