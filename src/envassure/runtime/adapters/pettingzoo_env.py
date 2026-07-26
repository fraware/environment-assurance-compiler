"""Optional PettingZoo adapter for multi-agent AssuredEnvironment."""

from __future__ import annotations

from typing import Any

from envassure.runtime.adapters.common import (
    AdapterSemanticsError,
    encode_observation,
    episode_termination_flags,
    legal_action_ids,
    observation_space_for_actor,
    require_world,
    resolve_action_ids,
    step_info,
)
from envassure.runtime.events import StepResult
from envassure.runtime.protocol import AssuredEnvironment
from envassure.runtime.rewards import RewardProvider, resolve_reward

_PZ_IMPORT_ERROR = (
    "pettingzoo is required for PettingZooAssureEnv. "
    "Install with: pip install envassure[pettingzoo]"
)
_GYM_IMPORT_ERROR = (
    "gymnasium is required for PettingZooAssureEnv observation/action spaces. "
    "Install with: pip install envassure[pettingzoo]"
)


def _import_pettingzoo() -> Any:
    try:
        import pettingzoo
    except ImportError as exc:
        raise ImportError(_PZ_IMPORT_ERROR) from exc
    return pettingzoo


def _import_gymnasium() -> Any:
    try:
        import gymnasium as gym
    except ImportError as exc:
        raise ImportError(_GYM_IMPORT_ERROR) from exc
    return gym


class PettingZooAssureEnv:
    """EXPERIMENTAL parallel-style multi-agent wrapper (EAC-09).

    **Not release-qualified.** PettingZoo conformance is deferred; do not claim
    trainer or PettingZoo API conformance. APIs may change without a deprecation
    cycle until a dedicated conformance track lands.

    PettingZoo is imported lazily. Agents map 1:1 to IR actor ids. Observation
    spaces come from IR projections (fail closed). Returned observations are
    encoded to match those spaces (enum → Discrete indices, etc.). Legal actions
    are derived from authorization + available actions via ``info`` /
    ``action_masks``.
    """

    metadata: dict[str, Any] = {
        "name": "envassure_pettingzoo_v0",
        "experimental": True,
        "conformance": "none",
    }

    def __init__(
        self,
        env: AssuredEnvironment,
        *,
        agent_action_map: dict[str, list[str]] | None = None,
        reward_provider: RewardProvider | None = None,
    ) -> None:
        _import_pettingzoo()
        gym = _import_gymnasium()
        self._env = env
        self._world = require_world(env)
        self._reward_provider = reward_provider

        if agent_action_map:
            self._agent_action_map = {
                agent: resolve_action_ids(self._world, agent, actions)
                for agent, actions in agent_action_map.items()
            }
        else:
            self._agent_action_map = {
                actor.id: list(actor.available_actions)
                for actor in self._world.actors
                if actor.available_actions
            }
            if not self._agent_action_map:
                raise AdapterSemanticsError(
                    "no actors with available_actions; pass agent_action_map explicitly"
                )

        self.possible_agents = list(self._agent_action_map.keys())
        self.agents: list[str] = []
        self.observation_spaces: dict[str, Any] = {
            agent: observation_space_for_actor(gym, self._world, agent)
            for agent in self.possible_agents
        }
        self.action_spaces: dict[str, Any] = {
            agent: gym.spaces.Discrete(len(self._agent_action_map[agent]))
            for agent in self.possible_agents
        }

    def _encode_agent_obs(self, agent: str, raw: dict[str, Any]) -> dict[str, Any]:
        obs = encode_observation(self._world, agent, raw)
        space = self.observation_spaces[agent]
        if not space.contains(obs):
            raise AdapterSemanticsError(
                f"encoded observation for {agent!r} is outside observation_space"
            )
        return obs

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        self._env.reset(seed=seed, options=options)
        self.agents = list(self.possible_agents)
        observations = {
            agent: self._encode_agent_obs(agent, self._env.observe(agent)) for agent in self.agents
        }
        infos: dict[str, dict[str, Any]] = {}
        for agent in self.agents:
            legal = legal_action_ids(self._env, agent)
            action_ids = self._agent_action_map[agent]
            infos[agent] = {
                "actor_id": agent,
                "outcome": None,
                "reason_code": None,
                "failure_id": None,
                "legal_actions": list(legal),
                "action_masks": [aid in set(legal) for aid in action_ids],
            }
        return observations, infos

    def step(
        self,
        actions: dict[str, int | str],
    ) -> tuple[
        dict[str, dict[str, Any]],
        dict[str, float],
        dict[str, bool],
        dict[str, bool],
        dict[str, dict[str, Any]],
    ]:
        observations: dict[str, dict[str, Any]] = {}
        rewards: dict[str, float] = {}
        terminations: dict[str, bool] = {}
        truncations: dict[str, bool] = {}
        infos: dict[str, dict[str, Any]] = {}

        for agent, action in actions.items():
            if agent not in self.agents:
                continue
            action_id = self._resolve_action(agent, action)
            result: StepResult = self._env.step(agent, action_id)
            observations[agent] = self._encode_agent_obs(agent, result.observation)
            reward, reward_status = resolve_reward(self._reward_provider, result, actor_id=agent)
            rewards[agent] = reward
            terminated, truncated = episode_termination_flags(result, self._env)
            terminations[agent] = terminated
            truncations[agent] = truncated
            legal = legal_action_ids(self._env, agent)
            infos[agent] = step_info(
                result,
                actor_id=agent,
                action_ids=self._agent_action_map[agent],
                legal=legal,
                reward_status=reward_status,
            )
            if result.terminal:
                for other in self.agents:
                    if other == agent:
                        continue
                    terminations.setdefault(other, terminated)
                    truncations.setdefault(other, truncated)
                    observations.setdefault(
                        other, self._encode_agent_obs(other, self._env.observe(other))
                    )
                    rewards.setdefault(other, 0.0)
                    other_legal = legal_action_ids(self._env, other)
                    infos.setdefault(
                        other,
                        {
                            "actor_id": other,
                            "outcome": result.outcome.value,
                            "reason_code": result.reason_code,
                            "failure_id": result.failure_id,
                            "legal_actions": list(other_legal),
                            "action_masks": [
                                aid in set(other_legal) for aid in self._agent_action_map[other]
                            ],
                        },
                    )
                self.agents = []
                break

        return observations, rewards, terminations, truncations, infos

    def observe(self, agent: str) -> dict[str, Any]:
        return self._encode_agent_obs(agent, self._env.observe(agent))

    def close(self) -> None:
        return None

    def _resolve_action(self, agent: str, action: int | str) -> str:
        if isinstance(action, str):
            return action
        action_ids = self._agent_action_map.get(agent) or []
        if not action_ids:
            raise AdapterSemanticsError(f"no actions configured for agent {agent!r}")
        if action < 0 or action >= len(action_ids):
            raise AdapterSemanticsError(f"action index {action} out of range for {agent!r}")
        return action_ids[action]
