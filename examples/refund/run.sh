#!/usr/bin/env bash
# Run the E1 refund example using an installed-wheel `eac` on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
OUT_DIR="${ROOT}/.example-out"
PACK_PATH="${OUT_DIR}/refund-authoring.eap"

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel, not only editable src)" >&2
  exit 1
fi

echo "==> eac --version"
eac --version

echo "==> reconcile + classic ambiguity (Python API)"
cd "${REPO_ROOT}"
python - <<'PY'
from examples.refund.world import (
    CLASSIC_REFUND_RETRY_AMBIGUITY_ID,
    find_amb_0042,
    reconcile_refund,
)

result = reconcile_refund()
amb = find_amb_0042(result)
assert amb.id == CLASSIC_REFUND_RETRY_AMBIGUITY_ID, amb.id
assert amb.status == "open", amb.status
print(amb.id)
print("ambiguities", len(result.ambiguities))
PY

echo "==> build-ir (open timeout/retry/idempotency gap remains explicit)"
eac build-ir \
  --module "${ROOT}/world.py" \
  -o "${OUT_DIR}/world.json"

echo "==> lint"
eac lint "${OUT_DIR}/world.json"

echo "==> run one modeled non-timeout submit_refund action"
eac run "${OUT_DIR}/world.json" \
  --actions agent:submit_refund \
  --seed 7 \
  --json > "${OUT_DIR}/run.json"
python - "${OUT_DIR}/run.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload["ok"] is True, payload
steps = payload.get("steps", [])
assert len(steps) == 1, steps
assert steps[0]["actor_id"] == "agent", steps[0]
assert steps[0]["action_id"] == "submit_refund", steps[0]
assert steps[0]["ok"] is True, steps[0]
print("runtime step ok")
PY

echo "==> package authoring-profile .eap (known gap intentionally unresolved)"
eac package "${OUT_DIR}/world.json" \
  -o "${PACK_PATH}" \
  --profile authoring \
  --json > "${OUT_DIR}/package.json"

echo "==> verify pack structure/integrity"
eac verify-pack "${PACK_PATH}" \
  --json > "${OUT_DIR}/verify-pack.json"

echo "run.sh completed; artifacts under ${OUT_DIR}"
