#!/usr/bin/env bash
# Verify E2 openenv_refund scaffold + pin expectations.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED="${ROOT}/expected/openenv-pin.json"
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

"$PYTHON_BIN" - <<'PY'
import json
from pathlib import Path

import yaml

from envassure.runtime.adapters.openenv_service import PINNED_OPENENV_VERSION

root = Path(".").resolve()
expected = json.loads((root / "expected" / "openenv-pin.json").read_text(encoding="utf-8"))
cfg = yaml.safe_load((root / "openenv.yaml").read_text(encoding="utf-8"))
assert cfg["openenv_pin"] == expected["openenv_pin"]
assert PINNED_OPENENV_VERSION == expected["openenv_pin"]
assert cfg["actor_id"] == expected["actor_id"]
for name in expected["required_members"]:
    path = root / name
    assert path.exists(), name
print("ok", expected["openenv_pin"])
PY

eac openenv test --dir . --json >/dev/null

echo "verify.sh passed"
