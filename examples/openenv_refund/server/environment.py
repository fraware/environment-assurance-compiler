"""Generated OpenEnv environment server (EnvAssure scaffold)."""

from __future__ import annotations

import json
from pathlib import Path

from envassure.ir.io import load_world
from envassure.runtime import EventSourcedEnvironment
from envassure.runtime.adapters.openenv_service import (
    EnvAssureOpenEnvAction,
    OpenEnvAssureService,
)

ROOT = Path(__file__).resolve().parents[1]
WORLD = load_world(ROOT / "world.json")
_BASE = EventSourcedEnvironment(WORLD, default_actor_id="client")
SERVICE = OpenEnvAssureService(_BASE, actor_id="client")


def reset(seed: int | None = None, options: dict | None = None) -> dict:
    return SERVICE.reset(seed=seed, options=options).model_dump(mode="json")


def step(action: dict) -> dict:
    return SERVICE.step(EnvAssureOpenEnvAction.model_validate(action)).model_dump(mode="json")


def state() -> dict:
    return SERVICE.state().model_dump(mode="json")


if __name__ == "__main__":
    print(json.dumps({"ok": True, "environment_id": WORLD.environment_id}))
