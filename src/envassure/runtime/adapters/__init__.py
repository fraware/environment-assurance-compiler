"""Optional framework adapters (Gymnasium, PettingZoo)."""

from __future__ import annotations

__all__ = [
    "GymAssureEnv",
    "PettingZooAssureEnv",
]


def __getattr__(name: str) -> type:
    if name == "GymAssureEnv":
        from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

        return GymAssureEnv
    if name == "PettingZooAssureEnv":
        from envassure.runtime.adapters.pettingzoo_env import PettingZooAssureEnv

        return PettingZooAssureEnv
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
