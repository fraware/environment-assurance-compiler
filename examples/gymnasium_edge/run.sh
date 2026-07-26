#!/usr/bin/env bash
# Run E5 gymnasium_edge using installed-wheel `eac` + envassure[gym].
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ROOT}/.example-out"
mkdir -p "${OUT_DIR}"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi
# shellcheck source=../_python.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_python.sh"

echo "==> eac --version"
eac --version

echo "==> compile world + write input/world.json"
"$PYTHON_BIN" world.py

echo "==> Gymnasium check_env + Dict action smoke"
"$PYTHON_BIN" - <<'PY'
from pathlib import Path

import gymnasium as gym
from gymnasium.utils.env_checker import check_env

from envassure.ir.io import load_world
from envassure.runtime import EventSourcedEnvironment
from envassure.runtime.adapters.gymnasium_env import GymAssureEnv, register_gymnasium_envs

root = Path(".").resolve()
world = load_world(root / "input" / "world.json")
inner = EventSourcedEnvironment(world, default_actor_id="agent")
env = GymAssureEnv(inner, actor_id="agent")
assert isinstance(env.action_space, gym.spaces.Dict), type(env.action_space)
check_env(env, skip_render_check=True)
obs, info = env.reset(seed=0)
assert env.observation_space.contains(obs)
obs, reward, terminated, truncated, info = env.step({"action_id": 0, "payload": {"value": 3}})
assert int(obs["n"]) == 3
assert info.get("reward_status") == "unconfigured"
register_gymnasium_envs()
env.close()
print("ok check_env + payload step")
PY

echo "run.sh completed; artifacts under ${OUT_DIR}"
