#!/usr/bin/env bash
# Verify E1 refund example expectations using installed-wheel `eac` on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
EXPECTED="${ROOT}/expected/ambiguity.json"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi

if [[ ! -f "${EXPECTED}" ]]; then
  echo "error: missing ${EXPECTED}" >&2
  exit 1
fi

for name in api.yaml refund-sop.md trace-0187.jsonl; do
  if [[ ! -f "${ROOT}/input/${name}" ]]; then
    echo "error: missing input/${name}" >&2
    exit 1
  fi
done

cd "${REPO_ROOT}"
python - <<'PY'
import json
from pathlib import Path

from examples.refund.world import (
    AMB_0042_ALIAS,
    CLASSIC_REFUND_RETRY_AMBIGUITY_ID,
    find_amb_0042,
    reconcile_refund,
)

root = Path("examples/refund")
expected = json.loads((root / "expected" / "ambiguity.json").read_text(encoding="utf-8"))
classic = expected["classic_retry_ambiguity"]
assert classic["fixture_alias"] == AMB_0042_ALIAS
assert classic["subject"] == "action:submit_refund"
assert classic["aspect"] == "retry_behavior"

result = reconcile_refund()
amb = find_amb_0042(result)
assert amb.id == CLASSIC_REFUND_RETRY_AMBIGUITY_ID, (amb.id, CLASSIC_REFUND_RETRY_AMBIGUITY_ID)
print("ok", amb.id)
PY

echo "verify.sh passed"
