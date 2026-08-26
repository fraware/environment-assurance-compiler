"""Release importer fixture corpus: fail-closed diagnostics and derivation honesty."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from typer.testing import CliRunner

from envassure.cli.app import app
from envassure.ir.primitives import origin_kind_for_derivation
from envassure.reconciliation import reconcile
from envassure.sources import import_source_report

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "importers"
_REPO = Path(__file__).resolve().parents[1]
_REFUND_SOURCES = _REPO / "examples" / "refund" / "sources"
_REFUND_INPUT = _REPO / "examples" / "refund" / "input"

_FAIL_CLOSED_CASES = [
    ("openapi", "malformed.yaml", {"EAC1004"}),
    ("openapi", "unsupported.yaml", {"EAC1006"}),
    ("procedure", "malformed.md", {"EAC1004"}),
    ("procedure", "unsupported.html", {"EAC1004"}),
    ("traces", "malformed.jsonl", {"EAC1004"}),
    ("traces", "unsupported.csv", {"EAC1004"}),
    ("database", "malformed.sql", {"EAC1004"}),
    ("database", "unsupported.sql", {"EAC1004"}),
    ("policy", "malformed.yaml", {"EAC1004"}),
    ("policy", "unsupported.yaml", {"EAC1006"}),
]

_PARTIAL_CASES = [
    ("openapi", "partial.yaml"),
    ("procedure", "partial.md"),
    ("traces", "partial.jsonl"),
    ("database", "partial.sql"),
    ("policy", "partial.yaml"),
]


def _fixture(kind: str, name: str) -> Path:
    path = _FIXTURES / kind / name
    assert path.is_file(), path
    return path


@pytest.mark.parametrize(("kind", "name", "expected_codes"), _FAIL_CLOSED_CASES)
def test_importer_fail_closed_diagnostics(
    kind: str,
    name: str,
    expected_codes: set[str],
) -> None:
    facts, report = import_source_report(kind, _fixture(kind, name))
    codes = {d.code for d in report.diagnostics}
    assert expected_codes & codes, f"expected one of {expected_codes}, got {codes}"
    if "EAC1004" in expected_codes and "EAC1004" in codes:
        assert facts == []


@pytest.mark.parametrize(("kind", "name"), _PARTIAL_CASES)
def test_importer_partial_parses_without_claiming_full_coverage(kind: str, name: str) -> None:
    facts, report = import_source_report(kind, _fixture(kind, name))
    assert not any(d.code == "EAC1004" for d in report.diagnostics)
    assert facts
    # Partial corpora must not invent direct coverage for inferred heuristics.
    for fact in facts:
        if fact.confidence.derivation_class == "inferred":
            assert fact.confidence.derivation_class != "direct"


def test_importer_conflicting_openapi_procedure_reconcile() -> None:
    openapi_facts, openapi_report = import_source_report(
        "openapi", _fixture("openapi", "conflicting.yaml")
    )
    procedure_facts, procedure_report = import_source_report(
        "procedure", _fixture("procedure", "conflicting.md")
    )
    assert not openapi_report.has_errors()
    assert not procedure_report.has_errors()

    openapi_retry = [f for f in openapi_facts if f.predicate == "retry_behavior"]
    procedure_retry = [f for f in procedure_facts if f.predicate == "retry_behavior"]
    assert len(openapi_retry) == 1
    assert openapi_retry[0].value == "retry_requires_status_check"
    assert openapi_retry[0].confidence.derivation_class == "inferred"
    assert len(procedure_retry) == 1
    assert procedure_retry[0].value == "retry_on_timeout"
    assert procedure_retry[0].confidence.derivation_class == "inferred"

    result = reconcile([*openapi_facts, *procedure_facts])
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes
    assert any(
        amb.subject == "action:submit_refund" and amb.aspect == "retry_behavior"
        for amb in result.unresolved_ambiguities
    )
    for amb in result.unresolved_ambiguities:
        assert amb.provenance.origin_kind == "unresolved_conflict"


def test_openapi_unspecified_retry_language_does_not_invent_policy() -> None:
    facts, report = import_source_report("openapi", _REFUND_INPUT / "api.yaml")
    assert not report.has_errors()
    assert not [f for f in facts if f.predicate == "retry_behavior"]

    timeout = [f for f in facts if f.predicate == "timeout_behavior"]
    assert len(timeout) == 1
    assert timeout[0].value == "http_504_timeout_response"
    assert timeout[0].confidence.derivation_class == "inferred"
    assert "no server-side state semantics are inferred" in (timeout[0].confidence.notes or "")


def test_importer_conflicting_policy_reconcile() -> None:
    facts, report = import_source_report("policy", _fixture("policy", "conflicting.yaml"))
    assert not report.has_errors()
    result = reconcile(facts)
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes


def test_importer_conflicting_database_reconcile() -> None:
    facts, report = import_source_report("database", _fixture("database", "conflicting.sql"))
    assert not report.has_errors()
    result = reconcile(facts)
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes


def test_importer_conflicting_traces_with_openapi_reconcile() -> None:
    openapi_facts, _ = import_source_report("openapi", _fixture("openapi", "conflicting.yaml"))
    trace_facts, report = import_source_report("traces", _fixture("traces", "conflicting.jsonl"))
    assert not report.has_errors()
    result = reconcile([*openapi_facts, *trace_facts])
    # Explicit OpenAPI retry policy may conflict with trace-derived safety evidence.
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes or result.unresolved_ambiguities


@pytest.mark.parametrize(
    ("kind", "name"),
    [
        ("openapi", "partial.yaml"),
        ("openapi", "conflicting.yaml"),
        ("openapi", "unsupported.yaml"),
        ("procedure", "conflicting.md"),
        ("traces", "partial.jsonl"),
        ("traces", "conflicting.jsonl"),
    ],
)
def test_inferred_facts_never_claim_direct(kind: str, name: str) -> None:
    facts, _report = import_source_report(kind, _fixture(kind, name))
    inferred = [f for f in facts if f.confidence.derivation_class == "inferred"]
    observed = [f for f in facts if f.confidence.derivation_class == "observed"]
    for fact in inferred:
        assert fact.confidence.derivation_class != "direct"
        assert origin_kind_for_derivation(fact.confidence.derivation_class) != "source_derived"
    for fact in observed:
        assert fact.confidence.derivation_class != "direct"
    # OpenAPI timeout/retry prose and procedure SOP heuristics must be inferred, not direct.
    if kind == "openapi" and any(f.predicate == "timeout_behavior" for f in facts):
        timeout = next(f for f in facts if f.predicate == "timeout_behavior")
        assert timeout.confidence.derivation_class == "inferred"
    if kind == "openapi" and any(f.predicate == "retry_behavior" for f in facts):
        retry = next(f for f in facts if f.predicate == "retry_behavior")
        assert retry.confidence.derivation_class == "inferred"
    if kind == "procedure" and any(f.predicate == "retry_behavior" for f in facts):
        retry = next(f for f in facts if f.predicate == "retry_behavior")
        assert retry.confidence.derivation_class == "inferred"


def test_unknown_adapter_kind_eac1005() -> None:
    facts, report = import_source_report(
        "not-a-real-adapter", _FIXTURES / "openapi" / "partial.yaml"
    )
    assert facts == []
    assert any(d.code == "EAC1005" for d in report.diagnostics)


def test_python_sdk_build_ir_authoring_round_trip(tmp_path: Path) -> None:
    runner = CliRunner()
    world_py = _REPO / "examples" / "counter" / "world.py"
    out = tmp_path / "world.json"
    result = runner.invoke(app, ["build-ir", "--module", str(world_py), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file()
    lint = runner.invoke(app, ["lint", str(out)])
    assert lint.exit_code == 0, lint.output


def test_refund_multisource_golden_path_reference() -> None:
    """examples/refund remains the multi-source conflict golden path."""
    root = _REPO / "examples" / "refund" / "world.py"
    spec = importlib.util.spec_from_file_location("refund_world_importers", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.reconcile_refund()
    codes = {d.code for d in result.diagnostics.diagnostics}
    assert "EAC2002" in codes
    amb = mod.find_amb_0042(result)
    assert amb.status == "open"
    assert amb.provenance.origin_kind == "unresolved_conflict"
    # Golden source trio is present for authors.
    assert (_REFUND_SOURCES / "api.yaml").is_file()
    assert (_REFUND_SOURCES / "refund-sop.md").is_file()
    assert (_REFUND_SOURCES / "trace-0187.jsonl").is_file()
