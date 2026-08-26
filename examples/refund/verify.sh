#!/usr/bin/env bash
# Verify E1 refund example expectations using installed-wheel `eac` on PATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${ROOT}/../.." && pwd)"
EXPECTED="${ROOT}/expected/ambiguity.json"
OUT_DIR="${ROOT}/.example-out"
WORKSPACE="${OUT_DIR}/workspace"
IR_PATH="${WORKSPACE}/ir/world.json"
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
  if [[ ! -f "${WORKSPACE}/sources/${name}" ]]; then
    echo "error: missing generated workspace source ${name}; run bash examples/refund/run.sh first" >&2
    exit 1
  fi
done

for name in \
  init.json import-openapi.json import-procedure.json import-traces.json \
  reconcile.json decision.json build-ir.json lint.json run.json package.json \
  verify-pack.json refund-authoring.eap; do
  if [[ ! -f "${OUT_DIR}/${name}" ]]; then
    echo "error: missing .example-out/${name}; run bash examples/refund/run.sh first" >&2
    exit 1
  fi
done

if [[ ! -f "${IR_PATH}" ]]; then
  echo "error: missing generated IR ${IR_PATH}" >&2
  exit 1
fi

# Re-run the public CLI verifier independently of run.sh's captured result.
eac verify-pack "${PACK_PATH}" --json > "${OUT_DIR}/verify-pack-repeat.json"

cd "${REPO_ROOT}"
python - "${ROOT}" "${OUT_DIR}" "${WORKSPACE}" <<'PY'
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
from envassure.reconciliation import ambiguity_id
from envassure.review import load_ambiguities, load_decisions_dir

root = Path(sys.argv[1])
out = Path(sys.argv[2])
workspace = Path(sys.argv[3])
expected = json.loads((root / "expected" / "ambiguity.json").read_text(encoding="utf-8"))
classic = expected["classic_retry_ambiguity"]
classic_id = ambiguity_id("action:submit_refund", "retry_behavior", "conflict")
assert classic["fixture_alias"] == "AMB-0042"
assert classic["subject"] == "action:submit_refund"
assert classic["aspect"] == "retry_behavior"

# Reconciliation must have failed closed before the decision, specifically on
# undefined retry semantics, while persisting the ambiguity artifact for review.
reconcile_payload = json.loads((out / "reconcile.json").read_text(encoding="utf-8"))
assert reconcile_payload["ok"] is False, reconcile_payload
assert reconcile_payload["exit_code"] != 0, reconcile_payload
assert any(d["code"] == "EAC4027" for d in reconcile_payload["diagnostics"])

ambiguities = load_ambiguities(workspace / "facts" / "ambiguities.json")
decided = next(a for a in ambiguities if a.id == classic_id)
assert decided.status == "accepted", decided
assert decided.decision_id, decided

decisions = {d.decision_id: d for d in load_decisions_dir(workspace / "decisions")}
decision = decisions[decided.decision_id]
assert decision.ambiguity_id == classic_id
assert decision.chosen_interpretation == "timeout_then_retry_requires_idempotency_key"
assert decision.expert_role == "example_author"
assert "modeling decision" in decision.rationale.lower()

# The imported source files are the actual public inputs, byte for byte.
for name in ("api.yaml", "refund-sop.md", "trace-0187.jsonl"):
    assert (workspace / "sources" / name).read_bytes() == (root / "input" / name).read_bytes()

for name in ("import-openapi.json", "import-procedure.json", "import-traces.json"):
    payload = json.loads((out / name).read_text(encoding="utf-8"))
    assert payload["ok"] is True, (name, payload)
    assert payload["imported_count"] > 0, (name, payload)

for name in ("build-ir.json", "lint.json"):
    payload = json.loads((out / name).read_text(encoding="utf-8"))
    assert payload["ok"] is True, (name, payload)

lint_payload = json.loads((out / "lint.json").read_text(encoding="utf-8"))
assert lint_payload["profile"] == "executable", lint_payload

world = load_world(workspace / "ir" / "world.json")
assert world.environment_id == "refund.v1"
assert world.declared_fidelity_level == "EF-0"
assert world.known_unsupported_behavior == ["live_payment_rail"]

state = next(item for item in world.state if item.id == "refund_status")
assert "sources/api.yaml" in state.provenance.source_ids

action = next(item for item in world.actions if item.id == "submit_refund")
assert action.retry_behavior == "timeout_then_retry_requires_idempotency_key"
assert action.idempotency == "idempotency_key_required"
assert action.timeout_behavior == "http_504_no_state_semantics"
assert action.provenance.origin_kind == "human_decision"
assert decided.decision_id in action.provenance.decision_ids
assert {
    "sources/api.yaml",
    "sources/refund-sop.md",
    "sources/trace-0187.jsonl",
} <= set(action.provenance.source_ids)

world_decided = next(item for item in world.ambiguities if item.id == classic_id)
assert world_decided.status == "accepted"
assert world_decided.decision_id == decided.decision_id

# Any other ambiguity remains visible; the example does not silently mark
# unrelated reconciliation records as resolved by the classic retry decision.
for ambiguity in world.ambiguities:
    if ambiguity.id != classic_id:
        assert ambiguity.status == "open", ambiguity

run_payload = json.loads((out / "run.json").read_text(encoding="utf-8"))
assert run_payload["ok"] is True
steps = run_payload["steps"]
assert len(steps) == 1
assert steps[0]["actor_id"] == "agent"
assert steps[0]["action_id"] == "submit_refund"
assert steps[0]["ok"] is True
assert run_payload["final_state"]["refund_status"] == "committed"

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
    item
    for item in provenance["elements"]
    if item["kind"] == "action" and item["id"] == "submit_refund"
)
assert packed_action["provenance"]["origin_kind"] == "human_decision"
assert decided.decision_id in packed_action["provenance"]["decision_ids"]
assert {
    "sources/api.yaml",
    "sources/refund-sop.md",
    "sources/trace-0187.jsonl",
} <= set(packed_action["provenance"]["source_ids"])

# No source-manifest metadata is fabricated. Because package was intentionally
# invoked without --sources-manifest/--workspace, the pack discloses that only
# semantic source ids are present and leaves their content digests unset.
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
assert claim.known_gaps == ["live_payment_rail"]
assert "EF-0" in claim.claim

print("verified E1 OpenAPI authoring contract", manifest.content_digest)
print("remaining open ambiguity records", [a.id for a in world.ambiguities if a.status == "open"])
PY

echo "verify.sh passed"
