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
  reconcile.json build-ir.json lint.json run.json package.json \
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

from envassure.facts.store import FactStore
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
from envassure.review import load_ambiguities

root = Path(sys.argv[1])
out = Path(sys.argv[2])
workspace = Path(sys.argv[3])
expected = json.loads((root / "expected" / "ambiguity.json").read_text(encoding="utf-8"))
classic = expected["classic_retry_ambiguity"]
classic_id = ambiguity_id("action:submit_refund", "retry_behavior", "conflict")
old_outcome_conflict_id = ambiguity_id("action:submit_refund", "observed_outcome", "conflict")
old_timeout_conflict_id = ambiguity_id("action:submit_refund", "timeout_behavior", "conflict")
assert classic["fixture_alias"] == "AMB-0042"
assert classic["subject"] == "action:submit_refund"
assert classic["aspect"] == "retry_behavior"

# Reconciliation must fail closed on the unresolved retry policy while still
# persisting the ambiguity for review.
reconcile_payload = json.loads((out / "reconcile.json").read_text(encoding="utf-8"))
assert reconcile_payload["ok"] is False, reconcile_payload
assert reconcile_payload["exit_code"] != 0, reconcile_payload
assert any(d["code"] == "EAC4027" for d in reconcile_payload["diagnostics"])

ambiguities = load_ambiguities(workspace / "facts" / "ambiguities.json")
action_conflicts = [
    a
    for a in ambiguities
    if a.subject == "action:submit_refund" and a.conflict_class == "semantic_conflict"
]
assert [a.id for a in action_conflicts] == [classic_id], [
    a.model_dump(mode="json") for a in action_conflicts
]
assert action_conflicts[0].status == "open"
assert action_conflicts[0].decision_id is None
assert old_outcome_conflict_id not in {a.id for a in ambiguities}
assert old_timeout_conflict_id not in {a.id for a in ambiguities}

# This public contract must not smuggle in a decision artifact to make the
# conflict disappear. The scoped model compiles by excluding unsupported fields.
assert not list((workspace / "decisions").glob("*.json"))

# The imported source files are the actual public inputs, byte for byte.
for name in ("api.yaml", "refund-sop.md", "trace-0187.jsonl"):
    assert (workspace / "sources" / name).read_bytes() == (root / "input" / name).read_bytes()

for name in ("import-openapi.json", "import-procedure.json", "import-traces.json"):
    payload = json.loads((out / name).read_text(encoding="utf-8"))
    assert payload["ok"] is True, (name, payload)
    assert payload["imported_count"] > 0, (name, payload)

# Audit the fact ontology itself, not only the downstream ambiguity count.
facts = FactStore.load(workspace / "facts" / "imported.json").list()
observed_outcomes = [f for f in facts if f.predicate == "observed_outcome"]
assert {f.value for f in observed_outcomes} == {"timeout", "observed_later", "ok"}
assert all(f.subject.kind == "trace_event" for f in observed_outcomes)
assert all(f.confidence.derivation_class == "observed" for f in observed_outcomes)
observed_actions = [f for f in facts if f.predicate == "observed_action"]
assert len(observed_actions) == 3
assert {f.value for f in observed_actions} == {"submit_refund"}
assert all(f.subject.kind == "trace_event" for f in observed_actions)

# Only the API contract supplies a canonical timeout_behavior candidate. SOP and
# trace timeout evidence are represented as acknowledgement/observations instead
# of false alternative definitions of the same canonical field.
timeout_facts = [
    f
    for f in facts
    if f.subject.kind == "action"
    and f.subject.id == "submit_refund"
    and f.predicate == "timeout_behavior"
]
assert len(timeout_facts) == 1, [f.model_dump(mode="json") for f in timeout_facts]
assert timeout_facts[0].confidence.evidence_class == "api_contract"
assert timeout_facts[0].confidence.derivation_class == "inferred"
assert any(f.predicate == "procedure_timeout_acknowledgement" for f in facts)
assert any(f.predicate == "observed_timeout" for f in facts)

# The retry disagreement remains real at the policy layer: the SOP instructs an
# unconditional retry, while the trace supports an inferred safety prohibition
# unless an idempotency key is used. Both heuristics must be labeled inferred.
retry_facts = [
    f
    for f in facts
    if f.subject.kind == "action"
    and f.subject.id == "submit_refund"
    and f.predicate == "retry_behavior"
]
assert {f.value for f in retry_facts} == {
    "retry_on_timeout",
    "do_not_retry_without_idempotency_key",
}
assert all(f.confidence.derivation_class == "inferred" for f in retry_facts)
assert any(
    f.predicate == "retry_guard_requirement"
    and f.value == "idempotency_key"
    and f.confidence.derivation_class == "inferred"
    for f in facts
)

for name in ("build-ir.json", "lint.json"):
    payload = json.loads((out / name).read_text(encoding="utf-8"))
    assert payload["ok"] is True, (name, payload)

lint_payload = json.loads((out / "lint.json").read_text(encoding="utf-8"))
assert lint_payload["profile"] == "executable", lint_payload

world = load_world(workspace / "ir" / "world.json")
assert world.environment_id == "refund.v1"
assert world.declared_fidelity_level == "EF-0"
assert world.known_unsupported_behavior == [
    "live_payment_rail",
    "timeout_retry_idempotency_semantics",
]

state = next(item for item in world.state if item.id == "refund_status")
assert "sources/api.yaml" in state.provenance.source_ids

action = next(item for item in world.actions if item.id == "submit_refund")
assert action.timeout_behavior is None
assert action.retry_behavior is None
assert action.idempotency is None
assert {
    "timeout_behavior",
    "retry_behavior",
    "idempotency",
    "authoritative_state_on_504",
} <= set(action.unsupported_semantics)
assert action.provenance.origin_kind == "inferred"
assert action.provenance.decision_ids == []
assert {
    "sources/api.yaml",
    "sources/refund-sop.md",
    "sources/trace-0187.jsonl",
} <= set(action.provenance.source_ids)

world_conflicts = [
    a
    for a in world.ambiguities
    if a.subject == "action:submit_refund" and a.conflict_class == "semantic_conflict"
]
assert [a.id for a in world_conflicts] == [classic_id]
assert world_conflicts[0].status == "open"
assert world_conflicts[0].decision_id is None

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
assert packed_action["provenance"]["origin_kind"] == "inferred"
assert packed_action["provenance"]["decision_ids"] == []
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
assert claim.known_gaps == [
    "live_payment_rail",
    "timeout_retry_idempotency_semantics",
]
assert "EF-0" in claim.claim

print("verified E1 OpenAPI scoped authoring contract", manifest.content_digest)
print("open action conflicts", [a.id for a in world_conflicts])
PY

echo "verify.sh passed"
