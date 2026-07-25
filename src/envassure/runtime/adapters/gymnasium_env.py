"""Optional Gymnasium adapter for AssuredEnvironment."""

from __future__ import annotations

from typing import Any

from envassure.runtime.events import StepResult
from envassure.runtime.protocol import AssuredEnvironment

_GYM_IMPORT_ERROR = (
    "gymnasium is required for GymAssureEnv. Install with: pip install envassure[gym]"
)


def _import_gymnasium() -> Any:
    try:
        import gymnasium as gym
    except ImportError as exc:
        raise ImportError(_GYM_IMPORT_ERROR) from exc
    return gym


class GymAssureEnv:
    """Thin Gymnasium Env wrapper around an AssuredEnvironment.

    Observation and action spaces are Dict/Discrete placeholders keyed by IR
    identifiers. External gymnasium is imported lazily.
    """

    metadata: dict[str, Any] = {"render_modes": []}

    def __init__(
        self,
        env: AssuredEnvironment,
        *,
        actor_id: str,
        action_ids: list[str] | None = None,
        render_mode: str | None = None,
    ) -> None:
        gym = _import_gymnasium()
        self._gym = gym
        self._env = env
        self._actor_id = actor_id
        self._action_ids = list(action_ids or [])
        self.render_mode = render_mode

        n_actions = max(len(self._action_ids), 1)
        self.action_space = gym.spaces.Discrete(n_actions)
        self.observation_space = gym.spaces.Dict({})

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        obs = self._env.reset(seed=seed, options=options)
        return obs, {"actor_id": self._actor_id}

    def step(self, action: int | str) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        action_id = self._resolve_action(action)
        result: StepResult = self._env.step(self._actor_id, action_id)
        reward = 1.0 if result.ok else -1.0
        terminated = result.terminal and not result.truncated
        truncated = result.truncated
        info = {
            **result.info,
            "ok": result.ok,
            "failure_id": result.failure_id,
            "events": [e.model_dump(mode="json") for e in result.events],
        }
        return result.observation, reward, terminated, truncated, info

    def render(self) -> None:
        return None

    def close(self) -> None:
        return None

    def _resolve_action(self, action: int | str) -> str:
        if isinstance(action, str):
            return action
        if not self._action_ids:
            raise ValueError("no action_ids configured for GymAssureEnv")
        if action < 0 or action >= len(self._action_ids):
            raise ValueError(f"action index {action} out of range")
        return self._action_ids[action]
