#!/usr/bin/env bash
# Verify E1 refund example expectations using installed-wheel `eac` on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
EXPECTED="${ROOT}/expected/ambiguity.json"
OUT_DIR="${ROOT}/.example-out"
PACK_PATH="${OUT_DIR}/refund-authoring.eap"

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

for name in world.json run.json package.json verify-pack.json refund-authoring.eap; do
  if [[ ! -f "${OUT_DIR}/${name}" ]]; then
    echo "error: missing .example-out/${name}; run ./examples/refund/run.sh first" >&2
    exit 1
  fi
done

# Re-run the public CLI verifier independently of run.sh's captured result.
eac verify-pack "${PACK_PATH}" --json > "${OUT_DIR}/verify-pack-repeat.json"

cd "${REPO_ROOT}"
python - "${ROOT}" "${OUT_DIR}" <<'PY'
import json
import sys
from pathlib import Path

from envassure.fidelity import FidelityLedger
from envassure.ir.io import load_world
from envassure.packaging import (
    PACK_MEMBER_FIDELITY,
    PACK_MEMBER_PROVENANCE,
    PACK_MEMBER_SOURCES,
    load_pack,
    verify_pack,
)
from examples.refund.world import (
    AMB_0042_ALIAS,
    CLASSIC_REFUND_RETRY_AMBIGUITY_ID,
    find_amb_0042,
    reconcile_refund,
)

root = Path(sys.argv[1])
out = Path(sys.argv[2])
expected = json.loads((root / "expected" / "ambiguity.json").read_text(encoding="utf-8"))
classic = expected["classic_retry_ambiguity"]
assert classic["fixture_alias"] == AMB_0042_ALIAS
assert classic["subject"] == "action:submit_refund"
assert classic["aspect"] == "retry_behavior"

# The authoritative reconciliation id stays hashed and open.
result = reconcile_refund()
amb = find_amb_0042(result)
assert amb.id == CLASSIC_REFUND_RETRY_AMBIGUITY_ID, (amb.id, CLASSIC_REFUND_RETRY_AMBIGUITY_ID)
assert amb.status == "open", amb.status

world = load_world(out / "world.json")
assert world.environment_id == "refund.v1"
assert world.declared_fidelity_level == "EF-0"
assert {
    "retry_after_timeout_without_decision",
    "idempotency_key_unspecified",
} <= set(world.known_unsupported_behavior)

state = next(item for item in world.state if item.id == "refund_status")
assert "input/api.yaml" in state.provenance.source_ids

action = next(item for item in world.actions if item.id == "submit_refund")
assert action.retry_behavior is None
assert action.idempotency is None
assert {
    "retry_behavior",
    "idempotency",
    "authoritative_state_on_504",
} <= set(action.unsupported_semantics)
assert {
    "input/api.yaml",
    "input/refund-sop.md",
    "input/trace-0187.jsonl",
} <= set(action.provenance.source_ids)

world_amb = next(item for item in world.ambiguities if item.id == AMB_0042_ALIAS)
assert world_amb.status == "open"

run_payload = json.loads((out / "run.json").read_text(encoding="utf-8"))
assert run_payload["ok"] is True
steps = run_payload["steps"]
assert len(steps) == 1
assert steps[0]["actor_id"] == "agent"
assert steps[0]["action_id"] == "submit_refund"
assert steps[0]["ok"] is True

package_payload = json.loads((out / "package.json").read_text(encoding="utf-8"))
assert package_payload["ok"] is True
assert package_payload["profile"] == "authoring"

for name in ("verify-pack.json", "verify-pack-repeat.json"):
    verify_payload = json.loads((out / name).read_text(encoding="utf-8"))
    assert verify_payload["ok"] is True, verify_payload
    assert verify_payload["diagnostics"] == [], verify_payload

pack_path = out / "refund-authoring.eap"
report = verify_pack(pack_path)
assert not report.has_errors(), [d.model_dump(mode="json") for d in report.diagnostics]
manifest, packed_world, members = load_pack(pack_path)
assert manifest.environment_id == "refund.v1"
assert packed_world == world

provenance = json.loads(members[PACK_MEMBER_PROVENANCE].decode("utf-8"))
packed_action = next(
    item for item in provenance["elements"] if item["kind"] == "action" and item["id"] == "submit_refund"
)
assert {
    "input/api.yaml",
    "input/refund-sop.md",
    "input/trace-0187.jsonl",
} <= set(packed_action["provenance"]["source_ids"])

# No sources.yml is fabricated for this example: the pack must say that only
# declared semantic source ids are present, with no invented content digests.
sources = json.loads(members[PACK_MEMBER_SOURCES].decode("utf-8"))
assert sources["environment_id"] == "refund.v1"
assert {entry["source_id"] for entry in sources["sources"]} == set(world.semantic_sources)
assert all(entry["digest"] is None for entry in sources["sources"])
assert any("No workspace sources.yml supplied" in note for note in sources["notes"])

ledger = FidelityLedger.model_validate_json(members[PACK_MEMBER_FIDELITY])
assert ledger.environment_id == "refund.v1"
assert len(ledger.claims) == 1
claim = ledger.claims[0]
assert claim.status == "structurally_valid"
assert claim.coverage == "declared_only"
assert claim.reviewer is None
assert {
    "retry_after_timeout_without_decision",
    "idempotency_key_unspecified",
} <= set(claim.known_gaps)

print("verified E1 OpenAPI authoring contract", manifest.content_digest)
PY

echo "verify.sh passed"
