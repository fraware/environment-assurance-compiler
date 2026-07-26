"""Optional framework adapters (Gymnasium, experimental PettingZoo)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "GymAssureEnv",
    "PettingZooAssureEnv",
    "register_gymnasium_envs",
]


def __getattr__(name: str) -> Any:
    if name == "GymAssureEnv":
        from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

        return GymAssureEnv
    if name == "PettingZooAssureEnv":
        from envassure.runtime.adapters.pettingzoo_env import PettingZooAssureEnv

        return PettingZooAssureEnv
    if name == "register_gymnasium_envs":
        from envassure.runtime.adapters.gymnasium_env import register_gymnasium_envs

        return register_gymnasium_envs
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
