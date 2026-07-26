#!/usr/bin/env bash
# Run the E1 refund example using an installed-wheel `eac` on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
OUT_DIR="${ROOT}/.example-out"
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
print(amb.id)
print("ambiguities", len(result.ambiguities))
PY

echo "==> build-ir (open conflict expected)"
eac build-ir \
  --module "${ROOT}/world.py" \
  -o "${OUT_DIR}/world.json"

echo "==> lint"
eac lint "${OUT_DIR}/world.json"

echo "run.sh completed; artifacts under ${OUT_DIR}"
