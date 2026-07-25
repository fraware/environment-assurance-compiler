"""Optional PettingZoo adapter for multi-agent AssuredEnvironment."""

from __future__ import annotations

from typing import Any

from envassure.runtime.events import StepResult
from envassure.runtime.protocol import AssuredEnvironment

_PZ_IMPORT_ERROR = (
    "pettingzoo is required for PettingZooAssureEnv. "
    "Install with: pip install envassure[pettingzoo]"
)


def _import_pettingzoo() -> Any:
    try:
        import pettingzoo
    except ImportError as exc:
        raise ImportError(_PZ_IMPORT_ERROR) from exc
    return pettingzoo


class PettingZooAssureEnv:
    """Parallel-style multi-agent wrapper around AssuredEnvironment.

    PettingZoo is imported lazily. Agents map 1:1 to IR actor ids.
    """

    metadata: dict[str, Any] = {"name": "envassure_pettingzoo_v0"}

    def __init__(
        self,
        env: AssuredEnvironment,
        *,
        agent_action_map: dict[str, list[str]] | None = None,
    ) -> None:
        _import_pettingzoo()
        self._env = env
        self._agent_action_map = dict(agent_action_map or {})
        self.possible_agents = list(self._agent_action_map.keys())
        self.agents: list[str] = []
        self.observation_spaces: dict[str, Any] = {}
        self.action_spaces: dict[str, Any] = {}

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        self._env.reset(seed=seed, options=options)
        self.agents = list(self.possible_agents)
        observations = {agent: self._env.observe(agent) for agent in self.agents}
        infos: dict[str, dict[str, Any]] = {agent: {} for agent in self.agents}
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
            observations[agent] = result.observation
            rewards[agent] = 1.0 if result.ok else -1.0
            terminations[agent] = result.terminal and not result.truncated
            truncations[agent] = result.truncated
            infos[agent] = {
                **result.info,
                "ok": result.ok,
                "failure_id": result.failure_id,
            }
            if result.terminal:
                for other in self.agents:
                    terminations.setdefault(other, True)
                    truncations.setdefault(other, result.truncated)
                    observations.setdefault(other, self._env.observe(other))
                    rewards.setdefault(other, 0.0)
                    infos.setdefault(other, {})
                self.agents = []
                break

        return observations, rewards, terminations, truncations, infos

    def observe(self, agent: str) -> dict[str, Any]:
        return self._env.observe(agent)

    def close(self) -> None:
        return None

    def _resolve_action(self, agent: str, action: int | str) -> str:
        if isinstance(action, str):
            return action
        action_ids = self._agent_action_map.get(agent) or []
        if not action_ids:
            raise ValueError(f"no actions configured for agent {agent!r}")
        if action < 0 or action >= len(action_ids):
            raise ValueError(f"action index {action} out of range for {agent!r}")
        return action_ids[action]
