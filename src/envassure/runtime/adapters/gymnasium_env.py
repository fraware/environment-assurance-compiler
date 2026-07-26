"""Optional Gymnasium adapter for AssuredEnvironment (release-qualified)."""

from __future__ import annotations

from typing import Any

from envassure.runtime.adapters.common import (
    AdapterSemanticsError,
    action_space_for_actor,
    decode_action,
    encode_observation,
    episode_termination_flags,
    evidence_digests,
    legal_action_ids,
    observation_space_for_actor,
    require_world,
    resolve_action_ids,
    step_info,
)
from envassure.runtime.events import StepResult
from envassure.runtime.protocol import AssuredEnvironment
from envassure.runtime.rewards import RewardProvider, resolve_reward

_GYM_IMPORT_ERROR = (
    "gymnasium is required for GymAssureEnv. Install with: pip install envassure[gym]"
)

_REGISTERED = False

try:
    import gymnasium as _gymnasium

    _GymEnvBase = _gymnasium.Env
except ImportError:  # pragma: no cover - exercised via monkeypatch / missing extra
    _gymnasium = None  # type: ignore[assignment]
    _GymEnvBase = object  # type: ignore[assignment,misc]


def _import_gymnasium() -> Any:
    if _gymnasium is None:
        try:
            import gymnasium as gym
        except ImportError as exc:
            raise ImportError(_GYM_IMPORT_ERROR) from exc
        return gym
    return _gymnasium


class GymAssureEnv(_GymEnvBase):  # type: ignore[misc,valid-type]
    """``gymnasium.Env`` subclass wrapping an AssuredEnvironment (EAC-09 / beta C1).

    Observation spaces are built from IR observation projections (fail closed on
    unsupported types/semantics). Returned observations are encoded to match those
    spaces. Actions without payloads use ``Discrete``; payload-bearing worlds use
    ``spaces.Dict`` with ``action_id`` + ``payload``. Rewards default to neutral
    (``reward_status="unconfigured"``) unless a :class:`RewardProvider` is supplied.
    """

    metadata: dict[str, Any] = {"render_modes": [], "name": "EnvAssure/GymAssure-v0"}

    def __init__(
        self,
        env: AssuredEnvironment,
        *,
        actor_id: str,
        action_ids: list[str] | None = None,
        render_mode: str | None = None,
        reward_provider: RewardProvider | None = None,
    ) -> None:
        gym = _import_gymnasium()
        self._gym = gym
        self._env = env
        self._actor_id = actor_id
        self._world = require_world(env)
        self._action_ids = resolve_action_ids(self._world, actor_id, action_ids)
        self._reward_provider = reward_provider
        self.render_mode = render_mode

        self.action_space = action_space_for_actor(
            gym, self._world, actor_id, self._action_ids
        )
        self.observation_space = observation_space_for_actor(gym, self._world, actor_id)

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if _GymEnvBase is not object:
            super().reset(seed=seed)
        self._env.reset(seed=seed, options=options)
        native = self._env.observe(self._actor_id)
        obs = encode_observation(self._world, self._actor_id, native)
        if not self.observation_space.contains(obs):
            raise AdapterSemanticsError(
                f"encoded observation for {self._actor_id!r} is outside observation_space"
            )
        legal = legal_action_ids(self._env, self._actor_id)
        info = {
            "actor_id": self._actor_id,
            "outcome": None,
            "reason_code": None,
            "failure_id": None,
            "legal_actions": list(legal),
            "action_masks": [aid in set(legal) for aid in self._action_ids],
            "reward_status": "unconfigured" if self._reward_provider is None else "configured",
            **evidence_digests(self._env, observation=native),
        }
        return obs, info

    def step(self, action: Any) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        action_id, payload = decode_action(
            action,
            action_ids=self._action_ids,
            action_space=self.action_space,
        )
        result: StepResult = self._env.step(self._actor_id, action_id, payload or None)
        reward, reward_status = resolve_reward(
            self._reward_provider,
            result,
            actor_id=self._actor_id,
        )
        terminated, truncated = episode_termination_flags(result, self._env)
        legal = legal_action_ids(self._env, self._actor_id)
        obs = encode_observation(self._world, self._actor_id, result.observation)
        if not self.observation_space.contains(obs):
            raise AdapterSemanticsError(
                f"encoded observation for {self._actor_id!r} is outside observation_space"
            )
        info = step_info(
            result,
            actor_id=self._actor_id,
            action_ids=self._action_ids,
            legal=legal,
            env=self._env,
            observation=result.observation,
            reward_status=reward_status,
            extra={"events": [e.model_dump(mode="json") for e in result.events]},
        )
        return obs, reward, terminated, truncated, info

    def render(self) -> None:
        return None

    def close(self) -> None:
        close = getattr(self._env, "close", None)
        if callable(close):
            close()


def register_gymnasium_envs() -> None:
    """Register stable ``EnvAssure/*`` Gymnasium environment IDs (idempotent)."""
    global _REGISTERED
    if _REGISTERED:
        return
    gym = _import_gymnasium()
    try:
        gym.register(
            id="EnvAssure/Generic-v0",
            entry_point="envassure.runtime.adapters.gymnasium_env:GymAssureEnv",
        )
    except Exception:
        # Already registered in this process.
        pass
    _REGISTERED = True
