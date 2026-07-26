#!/usr/bin/env bash
# Verify E5 gymnasium_edge expectations (installed wheel + gym extra).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED="${ROOT}/expected/check_env.json"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi
# shellcheck source=../_python.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_python.sh"

if [[ ! -f "${EXPECTED}" ]]; then
  echo "error: missing ${EXPECTED}" >&2
  exit 1
fi

if [[ ! -f input/world.json ]]; then
  "$PYTHON_BIN" world.py
fi

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

import gymnasium as gym
from gymnasium.utils.env_checker import check_env

from envassure.ir.io import load_world
from envassure.runtime import EventSourcedEnvironment
from envassure.runtime.adapters.gymnasium_env import GymAssureEnv

root = Path(".").resolve()
expected = json.loads((root / "expected" / "check_env.json").read_text(encoding="utf-8"))
world = load_world(root / "input" / "world.json")
assert world.environment_id == expected["environment_id"]
inner = EventSourcedEnvironment(world, default_actor_id=expected["actor_id"])
env = GymAssureEnv(inner, actor_id=expected["actor_id"])
assert isinstance(env.action_space, gym.spaces.Dict)
check_env(env, skip_render_check=True)
obs, _info = env.reset(seed=expected["seed"])
assert env.observation_space.contains(obs)
assert int(obs["n"]) == expected["initial_n"]
env.close()
print("ok", world.environment_id)
PY

echo "verify.sh passed"
