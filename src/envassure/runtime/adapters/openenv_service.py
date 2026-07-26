"""OpenEnv service adapter (best-effort; upstream API is experimental).

Pinned extra: ``openenv==0.4.1``. Unsupported semantics fail closed before startup.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.runtime.adapters.common import (
    AdapterSemanticsError,
    encode_observation,
    episode_termination_flags,
    evidence_digests,
    legal_action_ids,
    require_world,
    resolve_action_ids,
)
from envassure.runtime.protocol import AssuredEnvironment
from envassure.runtime.rewards import RewardProvider, resolve_reward

_OPENENV_IMPORT_ERROR = (
    "openenv is required for OpenEnvAssureService. "
    "Install with: pip install 'envassure[openenv]' (pins openenv==0.4.1)."
)

PINNED_OPENENV_VERSION = "0.4.1"


def _jsonable(value: Any) -> Any:
    """Convert numpy / nested containers to JSON-serializable Python values."""
    try:
        import numpy as np
    except ImportError:  # pragma: no cover
        np = None  # type: ignore[assignment]
    if np is not None:
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


class EnvAssureOpenEnvAction(BaseModel):
    """Typed action envelope exchanged with OpenEnv clients."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    actor_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnvAssureOpenEnvObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    observation: dict[str, Any] = Field(default_factory=dict)
    encoded: dict[str, Any] = Field(default_factory=dict)
    legal_actions: list[str] = Field(default_factory=list)
    reward: float = 0.0
    reward_status: str = "unconfigured"
    terminated: bool = False
    truncated: bool = False
    info: dict[str, Any] = Field(default_factory=dict)


class EnvAssureOpenEnvState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode_id: str | None = None
    seed: int | None = None
    authoritative_state: dict[str, Any] = Field(default_factory=dict)
    digests: dict[str, str] = Field(default_factory=dict)
    openenv_pin: str = PINNED_OPENENV_VERSION


def _import_openenv() -> Any:
    try:
        import openenv  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(_OPENENV_IMPORT_ERROR) from exc
    return openenv


def check_openenv_pin(*, require_exact: bool = False) -> dict[str, Any]:
    """Return installed openenv version metadata (fail closed if missing)."""
    openenv = _import_openenv()
    version = getattr(openenv, "__version__", None) or getattr(openenv, "VERSION", "unknown")
    ok = str(version) == PINNED_OPENENV_VERSION or not require_exact
    return {
        "installed": str(version),
        "pinned": PINNED_OPENENV_VERSION,
        "ok": ok if require_exact else True,
        "exact_match": str(version) == PINNED_OPENENV_VERSION,
    }


class OpenEnvAssureService:
    """Best-effort OpenEnv-facing service over AssuredEnvironment.

    Concurrent episodes are isolated via :meth:`fork`. Same-seed reset is
    deterministic when the underlying runtime is deterministic. Paths that
    depend on unstable upstream OpenEnv server APIs raise
    :class:`AdapterSemanticsError` (fail closed) rather than inventing behavior.
    """

    def __init__(
        self,
        env: AssuredEnvironment,
        *,
        actor_id: str,
        action_ids: list[str] | None = None,
        reward_provider: RewardProvider | None = None,
        require_exact_pin: bool = False,
    ) -> None:
        pin = check_openenv_pin(require_exact=require_exact_pin)
        if require_exact_pin and not pin["exact_match"]:
            raise AdapterSemanticsError(
                f"openenv version mismatch: installed={pin['installed']!r} "
                f"pinned={PINNED_OPENENV_VERSION!r}"
            )
        self._env = env
        self._world = require_world(env)
        self._actor_id = actor_id
        self._action_ids = resolve_action_ids(self._world, actor_id, action_ids)
        self._reward_provider = reward_provider
        self._seed: int | None = None
        self._episode_id: str | None = None
        self._openenv_meta = pin
        # Validate observation projections compile (fail closed on unsupported types).
        from envassure.runtime.adapters.common import observation_space_for_actor

        try:
            import gymnasium as gym
        except ImportError as exc:
            raise AdapterSemanticsError(
                "gymnasium is required to validate OpenEnv observation projections; "
                "install envassure[gym] or envassure[openenv]"
            ) from exc
        observation_space_for_actor(gym, self._world, actor_id)

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> EnvAssureOpenEnvObservation:
        self._seed = seed
        opts = dict(options or {})
        self._episode_id = str(opts.get("episode_id") or self._episode_id or "openenv-ep")
        self._env.reset(seed=seed, options=opts)
        return self._observe_envelope(reward=0.0, reward_status="unconfigured")

    def step(self, action: EnvAssureOpenEnvAction | dict[str, Any]) -> EnvAssureOpenEnvObservation:
        if isinstance(action, dict):
            action = EnvAssureOpenEnvAction.model_validate(action)
        if action.actor_id and action.actor_id != self._actor_id:
            raise AdapterSemanticsError(
                f"action actor_id {action.actor_id!r} != service actor {self._actor_id!r}"
            )
        if action.action_id not in self._action_ids:
            raise AdapterSemanticsError(f"unknown action_id {action.action_id!r}")
        result = self._env.step(self._actor_id, action.action_id, action.payload or None)
        reward, reward_status = resolve_reward(
            self._reward_provider, result, actor_id=self._actor_id
        )
        terminated, truncated = episode_termination_flags(result, self._env)
        env_obs = self._observe_envelope(
            reward=reward,
            reward_status=reward_status,
            observation=result.observation,
            terminated=terminated,
            truncated=truncated,
            extra_info={
                "outcome": result.outcome.value,
                "reason_code": result.reason_code,
                "failure_id": result.failure_id,
                "ok": result.ok,
            },
        )
        return env_obs

    def state(self) -> EnvAssureOpenEnvState:
        return EnvAssureOpenEnvState(
            episode_id=self._episode_id,
            seed=self._seed,
            authoritative_state=self._env.state(),
            digests=evidence_digests(self._env),
        )

    def fork_episode(self) -> OpenEnvAssureService:
        """Isolate a concurrent episode (fail closed if runtime cannot fork)."""
        forked = self._env.fork()
        return OpenEnvAssureService(
            forked,
            actor_id=self._actor_id,
            action_ids=list(self._action_ids),
            reward_provider=self._reward_provider,
        )

    def unsupported(self, feature: str) -> None:
        raise AdapterSemanticsError(
            f"OpenEnv feature {feature!r} is unsupported in envassure {PINNED_OPENENV_VERSION} "
            "pin (fail closed; upstream API still experimental)"
        )

    def _observe_envelope(
        self,
        *,
        reward: float,
        reward_status: str,
        observation: dict[str, Any] | None = None,
        terminated: bool = False,
        truncated: bool = False,
        extra_info: dict[str, Any] | None = None,
    ) -> EnvAssureOpenEnvObservation:
        native = observation if observation is not None else self._env.observe(self._actor_id)
        try:
            encoded = encode_observation(self._world, self._actor_id, native)
        except AdapterSemanticsError:
            # When reset runs before state init, empty observation may be invalid;
            # re-observe after reset always supplies paths.
            encoded = {}
            if native:
                raise
        legal = legal_action_ids(self._env, self._actor_id)
        info = {
            **evidence_digests(self._env, observation=native),
            "openenv_pin": self._openenv_meta,
            **(extra_info or {}),
        }
        return EnvAssureOpenEnvObservation(
            actor_id=self._actor_id,
            observation=_jsonable(native) if isinstance(native, dict) else {},
            encoded=_jsonable(encoded) if isinstance(encoded, dict) else {},
            legal_actions=legal,
            reward=reward,
            reward_status=reward_status,
            terminated=terminated,
            truncated=truncated,
            info=_jsonable(info),
        )
