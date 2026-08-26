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

    # Per-event observations are facts about trace_event entities, not canonical
    # action semantics. Each event retains an explicit observed_action link.
    outcomes = [f for f in facts if f.predicate == "observed_outcome"]
    assert {f.value for f in outcomes} == {"timeout", "observed_later", "ok"}
    assert all(f.subject.kind == "trace_event" for f in outcomes)
    assert all(f.confidence.derivation_class == "observed" for f in outcomes)
    event_links = [f for f in facts if f.predicate == "observed_action"]
    assert len(event_links) == 3
    assert all(f.subject.kind == "trace_event" for f in event_links)
    assert {f.value for f in event_links} == {"submit_refund"}

    # Safety heuristics are action-level inferences and must never claim direct
    # extraction from the trace.
    retry = [f for f in facts if f.predicate == "retry_behavior"]
    assert retry
    assert {f.value for f in retry} == {"do_not_retry_without_idempotency_key"}
    assert all(f.subject == EntityRef(kind="action", id="submit_refund") for f in retry)
    assert all(f.confidence.derivation_class == "inferred" for f in retry)
    guards = [f for f in facts if f.predicate == "retry_guard_requirement"]
    assert guards
    assert {f.value for f in guards} == {"idempotency_key"}
    assert all(f.confidence.derivation_class == "inferred" for f in guards)

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


def test_trace_observations_do_not_become_semantic_conflicts() -> None:
    path = (
        Path(__file__).resolve().parents[1] / "examples" / "refund" / "sources" / "trace-0187.jsonl"
    )
    facts = TraceAdapter().parse(path)
    result = reconcile(facts)

    # Heterogeneous empirical outcomes are separate events, not contradictory
    # action definitions. The reconciler must therefore emit no EAC2002 for them.
    assert not any(d.code == "EAC2002" for d in result.diagnostics.diagnostics)
    assert not any(a.conflict_class == "semantic_conflict" for a in result.ambiguities)
    accepted_outcomes = [f for f in result.accepted_facts if f.predicate == "observed_outcome"]
    assert {f.value for f in accepted_outcomes} == {"timeout", "observed_later", "ok"}
    assert all(f.subject.kind == "trace_event" for f in accepted_outcomes)


def test_trace_retry_inference_requires_prior_timeout(tmp_path: Path) -> None:
    ordinary = tmp_path / "ordinary.jsonl"
    ordinary.write_text(
        json.dumps(
            {
                "action": "submit_refund",
                "outcome": "ok",
                "state_effect": "committed",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ordinary_facts = TraceAdapter().parse(ordinary)
    assert not any(f.predicate == "retry_behavior" for f in ordinary_facts)
    assert not any(f.predicate == "retry_guard_requirement" for f in ordinary_facts)

    hazard = tmp_path / "hazard.jsonl"
    hazard.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "action": "submit_refund",
                        "outcome": "timeout",
                        "timeout": True,
                    }
                ),
                json.dumps(
                    {
                        "action": "submit_refund",
                        "outcome": "observed_later",
                        "state_effect": "committed",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    hazard_facts = TraceAdapter().parse(hazard)
    inferred = [f for f in hazard_facts if f.predicate == "retry_behavior"]
    assert len(inferred) == 1
    assert inferred[0].value == "do_not_retry_without_idempotency_key"
    assert inferred[0].confidence.derivation_class == "inferred"


def test_refund_ambiguity_amb_0042() -> None:
    mod = _refund_mod()
    result = mod.reconcile_refund()
    amb = mod.find_amb_0042(result)
    assert amb.status == "open"
    assert amb.id == mod.CLASSIC_REFUND_RETRY_AMBIGUITY_ID
    assert amb.id != "AMB-0042"  # production must not hard-code demo id
    assert "AMB-" in amb.id
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes
    assert "EAC4027" in codes

    # The classic retry policy disagreement is the semantic conflict. Event
    # outcomes and mere SOP/trace timeout observations must not manufacture
    # additional action-level conflicts.
    conflicts = [a for a in result.ambiguities if a.conflict_class == "semantic_conflict"]
    assert [a.id for a in conflicts] == [mod.CLASSIC_REFUND_RETRY_AMBIGUITY_ID]

    # Conflicted facts are not accepted into authoritative IR.
    assert all(
        f.subject.id != "submit_refund" or f.predicate != "retry_behavior"
        for f in result.accepted_facts
    )
    assert any(a.id == amb.id for a in result.unresolved_ambiguities)


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
    assert applied.decision.content_digest
    assert applied.decision.reviewer == "domain_expert"
    updated = next(a for a in applied.ambiguities if a.id == amb.id)
    assert updated.status == "accepted"
    save_decision_under(tmp_path, applied.decision)
    assert list(tmp_path.glob("*.json"))


def test_openapi_hardening_ref_params_security_certainty(tmp_path: Path) -> None:
    spec = tmp_path / "api.yaml"
    spec.write_text(
        """
openapi: "3.0.3"
info: {title: Demo, version: "1.0.0"}
security:
  - bearerAuth: []
paths:
  /items/{id}:
    parameters:
      - $ref: "#/components/parameters/ItemId"
    get:
      operationId: get_item
      callbacks:
        onEvent:
          "{$request.body#/url}":
            post:
              responses:
                "200": {description: ok}
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Item"
        "504":
          description: gateway timeout
components:
  parameters:
    ItemId:
      name: id
      in: path
      required: true
      schema: {type: string}
  schemas:
    Item:
      type: object
      properties:
        id: {type: string}
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
""".strip(),
        encoding="utf-8",
    )
    from envassure.sources.openapi import OpenAPIAdapter

    result = OpenAPIAdapter().parse_detailed(spec)
    facts = result.facts
    assert any(f.predicate == "http_parameters" for f in facts)
    assert any(f.predicate == "http_response_content" for f in facts)
    assert any(f.predicate == "auth_hint" for f in facts)
    timeout = next(f for f in facts if f.predicate == "timeout_behavior")
    assert timeout.confidence.derivation_class == "inferred"
    assert timeout.confidence.extractor_certainty in {"medium", "low"}
    direct = next(f for f in facts if f.predicate == "http_method")
    assert direct.confidence.derivation_class == "direct"
    assert direct.confidence.extractor_certainty == "high"
    assert any(d.code == "EAC1006" for d in result.diagnostics.diagnostics)
    certainties = {f.confidence.extractor_certainty for f in facts}
    assert certainties != {"high"}


def test_reconcile_no_amb_0042_hardcode() -> None:
    from envassure.reconciliation import ambiguity_id, reconcile

    facts = [
        SemanticFact(
            fact_id="a",
            subject=EntityRef(kind="action", id="submit_refund"),
            predicate="retry_behavior",
            value="retry",
            source_refs=["sop"],
            extraction_method="t",
            confidence=ConfidenceRecord(evidence_class="approved_procedure"),
        ),
        SemanticFact(
            fact_id="b",
            subject=EntityRef(kind="action", id="submit_refund"),
            predicate="retry_behavior",
            value="do_not_retry",
            source_refs=["api"],
            extraction_method="t",
            confidence=ConfidenceRecord(evidence_class="api_contract"),
        ),
    ]
    result = reconcile(facts)
    expected = ambiguity_id("action:submit_refund", "retry_behavior", "conflict")
    conflict = next(a for a in result.ambiguities if a.conflict_class == "semantic_conflict")
    assert conflict.id == expected
    assert conflict.id != "AMB-0042"
    assert not any(a.id == "AMB-0042" for a in result.ambiguities)
    assert result.accepted_facts == []
    assert result.unresolved_ambiguities


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
