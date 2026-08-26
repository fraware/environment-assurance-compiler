#!/usr/bin/env bash
# Run the E1 refund example using an installed-wheel `eac` on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
OUT_DIR="${ROOT}/.example-out"
WORKSPACE="${OUT_DIR}/workspace"
IR_PATH="${WORKSPACE}/ir/world.json"
PACK_PATH="${OUT_DIR}/refund-authoring.eap"

rm -rf "${OUT_DIR}"
mkdir -p "${OUT_DIR}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel, not only editable src)" >&2
  exit 1
fi

cd "${REPO_ROOT}"

echo "==> eac --version"
eac --version

echo "==> initialize disposable author workspace"
eac init "${WORKSPACE}" --name refund-example --json > "${OUT_DIR}/init.json"
cp "${ROOT}/input/api.yaml" "${WORKSPACE}/sources/api.yaml"
cp "${ROOT}/input/refund-sop.md" "${WORKSPACE}/sources/refund-sop.md"
cp "${ROOT}/input/trace-0187.jsonl" "${WORKSPACE}/sources/trace-0187.jsonl"

echo "==> import OpenAPI, approved procedure, and operational trace"
eac import openapi "${WORKSPACE}/sources/api.yaml" \
  --path "${WORKSPACE}" --merge --json > "${OUT_DIR}/import-openapi.json"
eac import procedure "${WORKSPACE}/sources/refund-sop.md" \
  --path "${WORKSPACE}" --merge --json > "${OUT_DIR}/import-procedure.json"
eac import traces "${WORKSPACE}/sources/trace-0187.jsonl" \
  --path "${WORKSPACE}" --merge --json > "${OUT_DIR}/import-traces.json"

echo "==> reconcile (EAC4027 is expected and must fail closed before decision)"
set +e
eac facts --path "${WORKSPACE}" --reconcile --json > "${OUT_DIR}/reconcile.json"
RECONCILE_RC=$?
set -e
if [[ "${RECONCILE_RC}" -eq 0 ]]; then
  echo "error: unresolved refund retry semantics unexpectedly reconciled without a blocking diagnostic" >&2
  exit 1
fi

CLASSIC_ID="$(python - <<'PY'
from envassure.reconciliation import ambiguity_id
print(ambiguity_id("action:submit_refund", "retry_behavior", "conflict"))
PY
)"

python - "${OUT_DIR}/reconcile.json" "${WORKSPACE}/facts/ambiguities.json" "${CLASSIC_ID}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
ambiguities = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
classic_id = sys.argv[3]
records = ambiguities if isinstance(ambiguities, list) else ambiguities.get("ambiguities", [])

assert payload["ok"] is False, payload
assert payload["exit_code"] != 0, payload
assert any(d["code"] == "EAC4027" for d in payload["diagnostics"]), payload["diagnostics"]
classic = next(a for a in records if a["id"] == classic_id)
assert classic["status"] == "open", classic
assert classic["subject"] == "action:submit_refund", classic
assert classic["conflict_class"] == "semantic_conflict", classic
print("expected pre-decision failure:", classic_id)
for ambiguity in records:
    print(
        "ambiguity",
        ambiguity["id"],
        ambiguity["conflict_class"],
        ambiguity["subject"],
        ambiguity["status"],
    )
PY

echo "==> record explicit example-author decision for classic retry conflict"
eac decide "${CLASSIC_ID}" \
  --path "${WORKSPACE}" \
  --interpretation timeout_then_retry_requires_idempotency_key \
  --role example_author \
  --rationale "For this executable example, reconcile the SOP retry instruction with the double-apply trace by requiring an idempotency key; this is a modeling decision, not a production-fidelity claim." \
  --json > "${OUT_DIR}/decision.json"

# The template refuses to build unless the accepted ambiguity and persisted
# decision artifact are present in the workspace.
cp "${ROOT}/decided_world.py" "${WORKSPACE}/world.py"

echo "==> build typed IR after explicit decision"
eac build-ir --path "${WORKSPACE}" --force --json > "${OUT_DIR}/build-ir.json"

echo "==> lint executable semantics"
eac lint "${IR_PATH}" --profile executable --force --json > "${OUT_DIR}/lint.json"

echo "==> run one modeled submit_refund action"
eac run "${IR_PATH}" \
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
assert payload["final_state"]["refund_status"] == "committed", payload["final_state"]
print("runtime step ok")
PY

echo "==> package authoring-profile .eap (EF-0; live payment rail remains unsupported)"
eac package "${IR_PATH}" \
  -o "${PACK_PATH}" \
  --profile authoring \
  --json > "${OUT_DIR}/package.json"

echo "==> verify pack structure/integrity"
eac verify-pack "${PACK_PATH}" \
  --json > "${OUT_DIR}/verify-pack.json"

echo "run.sh completed; artifacts under ${OUT_DIR}"
