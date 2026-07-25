"""Phase 2: adapters, facts, reconciliation, refund conflict."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from envassure.facts.models import ConfidenceRecord, SemanticFact
from envassure.facts.store import FactStore
from envassure.ir.primitives import EntityRef
from envassure.reconciliation import reconcile
from envassure.review import apply_decision, save_decision_under
from envassure.sources import SourceParseError, import_source
from envassure.sources.traces import TraceAdapter
from envassure.workspace.config import SourcePrecedenceSection


def _refund_mod():
    root = Path(__file__).resolve().parents[1] / "examples" / "refund" / "world.py"
    spec = importlib.util.spec_from_file_location("refund_world", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_openapi_import_produces_facts() -> None:
    api = Path(__file__).resolve().parents[1] / "examples" / "refund" / "sources" / "api.yaml"
    facts = import_source("openapi", api)
    assert facts
    assert any(f.subject.id == "submit_refund" for f in facts)
    assert any(f.predicate == "timeout_behavior" for f in facts)
    assert any(f.subject.kind == "schema" for f in facts)
    assert all(isinstance(f.confidence, ConfidenceRecord) for f in facts)


def test_fact_store_roundtrip(tmp_path: Path) -> None:
    store = FactStore()
    store.add(
        SemanticFact(
            fact_id="f1",
            subject=EntityRef(kind="action", id="submit_refund"),
            predicate="timeout_behavior",
            value="unknown",
            source_refs=["api.yaml"],
            extraction_method="openapi",
            confidence=ConfidenceRecord(
                evidence_class="api_contract",
                extractor_certainty="high",
                conflict_status="none",
                reviewer_status="unreviewed",
            ),
            status="candidate",
        )
    )
    path = tmp_path / "facts.json"
    store.save(path)
    loaded = FactStore.load(path)
    assert len(loaded) == 1
    assert loaded.get("f1") is not None


def test_streaming_traces(tmp_path: Path) -> None:
    path = (
        Path(__file__).resolve().parents[1] / "examples" / "refund" / "sources" / "trace-0187.jsonl"
    )
    facts = TraceAdapter().parse(path)
    assert facts
    assert any(f.predicate == "event_count" for f in facts)

    # Line-by-line: large file still parses without requiring array load.
    big = tmp_path / "big.jsonl"
    with big.open("w", encoding="utf-8") as handle:
        for i in range(100):
            handle.write(json.dumps({"action": "submit_refund", "outcome": "ok", "i": i}) + "\n")
    assert any(f.predicate == "event_count" and f.value == 100 for f in TraceAdapter().parse(big))

    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not-json\n", encoding="utf-8")
    try:
        TraceAdapter().parse(bad)
        raise AssertionError("expected SourceParseError")
    except SourceParseError:
        pass


def test_refund_ambiguity_amb_0042() -> None:
    mod = _refund_mod()
    result = mod.reconcile_refund()
    amb = mod.find_amb_0042(result)
    assert amb.status == "open"
    assert amb.id == "AMB-0042"
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes
    assert "EAC4027" in codes


def test_apply_decision(tmp_path: Path) -> None:
    mod = _refund_mod()
    result = mod.reconcile_refund()
    amb = mod.find_amb_0042(result)
    applied = apply_decision(
        result.ambiguities,
        ambiguity_id=amb.id,
        chosen_interpretation=amb.candidate_interpretations[0]
        if amb.candidate_interpretations
        else "do_not_retry_without_status_check",
        expert_role="domain_expert",
        rationale="Align with idempotent commit check before retry.",
    )
    assert not applied.diagnostics.has_errors()
    assert applied.decision is not None
    updated = next(a for a in applied.ambiguities if a.id == amb.id)
    assert updated.status == "accepted"
    save_decision_under(tmp_path, applied.decision)
    assert list(tmp_path.glob("*.json"))


def test_precedence_orders_candidates() -> None:
    facts = [
        SemanticFact(
            fact_id="a",
            subject=EntityRef(kind="action", id="x"),
            predicate="retry_behavior",
            value="retry",
            source_refs=["sop"],
            extraction_method="t",
            confidence=ConfidenceRecord(evidence_class="approved_procedure"),
        ),
        SemanticFact(
            fact_id="b",
            subject=EntityRef(kind="action", id="x"),
            predicate="retry_behavior",
            value="do_not_retry",
            source_refs=["api"],
            extraction_method="t",
            confidence=ConfidenceRecord(evidence_class="api_contract"),
        ),
    ]
    result = reconcile(facts, SourcePrecedenceSection())
    conflict = next(a for a in result.ambiguities if a.conflict_class == "semantic_conflict")
    assert "api_contract" in conflict.candidate_interpretations[0]
