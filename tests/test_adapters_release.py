"""EAC-09 release tests for Gymnasium and PettingZoo adapters."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from envassure.runtime import EventSourcedEnvironment

REPO = Path(__file__).resolve().parents[1]


def _load_example_world(rel: str, attr: str) -> Any:
    root = REPO / rel
    spec = importlib.util.spec_from_file_location(f"ex_{attr}", root)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, attr)()


@pytest.fixture
def counter_world() -> Any:
    return _load_example_world("examples/counter/world.py", "build_counter_world")


@pytest.mark.gym
def test_gym_counter_term_trunc_obs_legal_reason(counter_world: Any) -> None:
    pytest.importorskip("gymnasium")
    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    inner = EventSourcedEnvironment(counter_world, default_actor_id="client")
    env = GymAssureEnv(inner, actor_id="client")

    assert "count" in env.observation_space.spaces
    assert env.action_space.n == 3  # increment, reset, get from IR

    obs, info = env.reset(seed=0, options={"task_id": "reach_three", "episode_id": "gym-counter"})
    assert env.observation_space.contains(obs)
    assert int(obs["count"]) == 0
    assert info["reason_code"] is None
    assert info["outcome"] is None
    assert info["failure_id"] is None
    assert "increment" in info["legal_actions"]
    assert "get" in info["legal_actions"]
    assert "reset" not in info["legal_actions"]
    assert info["action_masks"] == [
        aid in set(info["legal_actions"]) for aid in ["increment", "reset", "get"]
    ]

    # Unauthorized reset still surfaces outcome / reason / failure_id.
    _obs, _reward, terminated, truncated, denied_info = env.step("reset")
    assert env.observation_space.contains(_obs)
    assert terminated is False
    assert truncated is False
    assert denied_info["outcome"] == "denied"
    assert denied_info["reason_code"]
    assert denied_info["failure_id"]
    assert "reset" not in denied_info["legal_actions"]

    for _ in range(3):
        obs, reward, terminated, truncated, info = env.step("increment")
        assert env.observation_space.contains(obs)
        assert reward == 0.0
        assert info["reward_status"] == "unconfigured"
        assert info["outcome"] in {"success", "truncated"}
        assert "state_digest" in info
        assert info["reason_code"] is not None
        assert "failure_id" in info
        assert "action_masks" in info
        assert "legal_actions" in info

    assert int(obs["count"]) == 3
    assert terminated is True
    assert truncated is False
    record = inner.terminal_record
    assert record is not None
    assert record.terminal is True
    assert record.truncated is False
    assert record.goal_reached is True


@pytest.mark.gym
def test_gym_enum_observation_round_trip_and_contains() -> None:
    """Enum Discrete spaces must receive encoded indices, not string labels."""
    pytest.importorskip("gymnasium")
    from envassure.runtime.adapters.common import (
        AdapterSemanticsError,
        decode_observation,
        encode_observation,
    )
    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    auth_world = _load_example_world("examples/auth/world.py", "build_auth_world")
    requester = "requester"
    inner = EventSourcedEnvironment(auth_world, default_actor_id=requester)
    env = GymAssureEnv(inner, actor_id=requester)

    assert str(env.observation_space.spaces["request_status"])  # Discrete
    obs, _info = env.reset(seed=0, options={"episode_id": "gym-enum", "task_id": "get_approval"})
    assert env.observation_space.contains(obs)
    assert obs["request_status"] == 0  # draft
    assert decode_observation(auth_world, "requester", obs) == {"request_status": "draft"}

    obs, _reward, _term, _trunc, info = env.step("submit")
    assert env.observation_space.contains(obs)
    assert obs["request_status"] == 1  # pending
    assert info["outcome"] == "success"
    assert decode_observation(auth_world, "requester", obs)["request_status"] == "pending"

    with pytest.raises(AdapterSemanticsError, match="not in enum_values"):
        encode_observation(auth_world, "requester", {"request_status": "nope"})


@pytest.mark.gym
def test_gym_text_scalar_observation_contains() -> None:
    pytest.importorskip("gymnasium")
    import gymnasium as gym

    from envassure.runtime.adapters.common import observation_space_for_actor
    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    auth_world = _load_example_world("examples/auth/world.py", "build_auth_world")
    space = observation_space_for_actor(gym, auth_world, "approver")
    assert isinstance(space.spaces["requester_id"], gym.spaces.Text)
    assert isinstance(space.spaces["request_status"], gym.spaces.Discrete)

    approver = "approver"
    inner = EventSourcedEnvironment(auth_world, default_actor_id=approver)
    env = GymAssureEnv(inner, actor_id=approver)
    obs, _info = env.reset(seed=0, options={"episode_id": "gym-text"})
    assert env.observation_space.contains(obs)
    assert obs["requester_id"] == ""
    assert obs["request_status"] == 0


@pytest.mark.gym
def test_gym_counter_horizon_truncation(counter_world: Any) -> None:
    pytest.importorskip("gymnasium")
    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    inner = EventSourcedEnvironment(counter_world, default_actor_id="client")
    env = GymAssureEnv(inner, actor_id="client", action_ids=["get"])
    env.reset(seed=1, options={"task_id": "reach_three", "episode_id": "gym-trunc"})

    # Horizon is 10; only `get` does not advance the goal.
    terminated = False
    truncated = False
    info: dict[str, Any] = {}
    for _ in range(10):
        _obs, _reward, terminated, truncated, info = env.step("get")
    assert truncated is True
    assert terminated is False
    assert info["outcome"] == "truncated"
    assert info["reason_code"] == "truncated"
    assert "failure_id" in info
    record = inner.terminal_record
    assert record is not None
    assert record.truncated is True


@pytest.mark.gym
def test_gym_fails_closed_on_unsupported_observation() -> None:
    pytest.importorskip("gymnasium")
    from envassure.api import World
    from envassure.runtime.adapters.common import AdapterSemanticsError
    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    w = World("bad.obs.v1", "BadObs")
    w.state("blob", type="opaque_external_ref")
    w.actor("a", available_actions=["noop"], observation_projection_id="view")
    w.observation("view", target_actor_class="a", visible_paths=["blob"])
    w.action("noop", actor_classes=["a"], success_outcomes=["ok"])
    w.transition("t_noop", action_id="noop", events=["noop"])
    world = w.compile()
    inner = EventSourcedEnvironment(world)
    with pytest.raises(AdapterSemanticsError, match="unsupported type"):
        GymAssureEnv(inner, actor_id="a")


@pytest.fixture
def auth_world() -> Any:
    return _load_example_world("examples/auth/world.py", "build_auth_world")


@pytest.mark.pettingzoo
def test_pettingzoo_auth_multi_actor_legal_obs_reason(auth_world: Any) -> None:
    """PettingZoo release coverage on the real multi-actor auth example."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from envassure.runtime.adapters.pettingzoo_env import PettingZooAssureEnv

    inner = EventSourcedEnvironment(auth_world)
    env = PettingZooAssureEnv(inner)

    assert set(env.possible_agents) == {"requester", "approver"}
    assert "request_status" in env.observation_spaces["requester"].spaces
    assert "request_status" in env.observation_spaces["approver"].spaces
    assert env.action_spaces["requester"].n == 2  # submit, observe
    assert env.action_spaces["approver"].n == 3  # approve, deny, observe

    observations, infos = env.reset(
        seed=0,
        options={"episode_id": "pz-auth", "task_id": "get_approval"},
    )
    assert set(observations) == {"requester", "approver"}
    assert env.observation_spaces["requester"].contains(observations["requester"])
    assert env.observation_spaces["approver"].contains(observations["approver"])
    assert observations["requester"] == {"request_status": 0}  # draft
    assert observations["approver"]["request_status"] == 0
    assert observations["approver"]["requester_id"] == ""
    for agent in env.agents:
        assert "reason_code" in infos[agent]
        assert "outcome" in infos[agent]
        assert "failure_id" in infos[agent]
        assert "legal_actions" in infos[agent]
        assert "action_masks" in infos[agent]

    assert "submit" in infos["requester"]["legal_actions"]
    assert "approve" not in infos["requester"]["legal_actions"]
    assert "approve" in infos["approver"]["legal_actions"]
    assert "deny" in infos["approver"]["legal_actions"]

    observations, rewards, terminations, truncations, infos = env.step({"requester": "submit"})
    assert rewards["requester"] == 0.0
    assert infos["requester"]["outcome"] == "success"
    assert infos["requester"]["reason_code"] is not None
    assert "failure_id" in infos["requester"]
    assert terminations.get("requester") is False
    assert truncations.get("requester") is False
    assert observations["requester"]["request_status"] == 1  # pending
    assert env.observe("approver")["request_status"] == 1
    assert env.observation_spaces["approver"].contains(env.observe("approver"))

    # Requester cannot select approve (not in available_actions); still surfaces info.
    _obs, _rewards, _term, _trunc, denied = env.step({"requester": "approve"})
    assert denied["requester"]["outcome"] == "invalid_input"
    assert denied["requester"]["reason_code"]
    assert denied["requester"]["failure_id"]
    assert "approve" not in denied["requester"]["legal_actions"]

    observations, rewards, terminations, truncations, infos = env.step({"approver": "approve"})
    assert rewards["approver"] == 0.0
    assert infos["approver"]["outcome"] == "success"
    assert infos["approver"]["reason_code"] is not None
    assert "failure_id" in infos["approver"]
    assert observations["approver"]["request_status"] == 2  # approved
    assert env.observation_spaces["approver"].contains(observations["approver"])
    assert len(infos["approver"]["action_masks"]) == env.action_spaces["approver"].n
    assert truncations.get("approver") is False


@pytest.mark.gym
def test_gym_is_gymnasium_env_subclass() -> None:
    pytest.importorskip("gymnasium")
    import gymnasium as gym

    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    assert issubclass(GymAssureEnv, gym.Env)


@pytest.mark.gym
def test_gym_check_env_counter(counter_world: Any) -> None:
    pytest.importorskip("gymnasium")
    from gymnasium.utils.env_checker import check_env

    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

    inner = EventSourcedEnvironment(counter_world, default_actor_id="client")
    env = GymAssureEnv(inner, actor_id="client")
    # skip_render: we declare empty render_modes
    check_env(env, skip_render_check=True)


@pytest.mark.gym
def test_gym_payload_dict_action_space_and_malformed() -> None:
    pytest.importorskip("gymnasium")
    import gymnasium as gym

    from envassure.api import World
    from envassure.runtime.adapters.common import AdapterSemanticsError, decode_action
    from envassure.runtime.adapters.gymnasium_env import GymAssureEnv
    from envassure.runtime.rewards import OutcomeRewardProvider

    w = World("payload.v1", "Payload")
    w.state("n", type="resource_counter", initial_generator="0")
    w.actor("a", available_actions=["set"], observation_projection_id="view")
    w.observation("view", target_actor_class="a", visible_paths=["n"])
    w.action(
        "set",
        actor_classes=["a"],
        writes=["n"],
        intended_effects=["n = payload.value"],
        input_schema={
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "integer", "minimum": 0, "maximum": 10}},
            "additionalProperties": False,
        },
        success_outcomes=["ok"],
    )
    w.transition("t_set", action_id="set", events=["set"])
    world = w.compile()
    inner = EventSourcedEnvironment(world, default_actor_id="a")
    env = GymAssureEnv(
        inner,
        actor_id="a",
        reward_provider=OutcomeRewardProvider(),
    )
    assert isinstance(env.action_space, gym.spaces.Dict)
    assert "action_id" in env.action_space.spaces
    assert "payload" in env.action_space.spaces

    obs, info = env.reset(seed=0)
    assert env.observation_space.contains(obs)
    assert info["reward_status"] == "configured"

    obs, reward, term, _trunc, info = env.step({"action_id": 0, "payload": {"value": 3}})
    assert reward == 1.0
    assert info["reward_status"] == "configured"
    assert int(obs["n"]) == 3
    assert term is False

    with pytest.raises(AdapterSemanticsError, match=r"malformed|out of range|Dict action"):
        decode_action({"payload": {}}, action_ids=["set"], action_space=env.action_space)

    with pytest.raises(AdapterSemanticsError, match="out of range"):
        env.step(99)


@pytest.mark.gym
def test_gym_register_idempotent() -> None:
    pytest.importorskip("gymnasium")
    from envassure.runtime.adapters.gymnasium_env import register_gymnasium_envs

    register_gymnasium_envs()
    register_gymnasium_envs()


@pytest.mark.pettingzoo
def test_pettingzoo_marked_experimental(auth_world: Any) -> None:
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from envassure.runtime.adapters.pettingzoo_env import PettingZooAssureEnv

    inner = EventSourcedEnvironment(auth_world)
    env = PettingZooAssureEnv(inner)
    assert env.metadata.get("experimental") is True
    assert "EXPERIMENTAL" in (PettingZooAssureEnv.__doc__ or "")
