"""Tests for diagnostic models, catalog, and factory."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from envassure.diagnostics.catalog import (
    DIAGNOSTIC_CATALOG,
    FAMILY_DOCS,
    get_definition,
    require_documented,
)
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic, DiagnosticReport, Severity
from envassure.diagnostics.render import format_diagnostic, format_report


def test_catalog_covers_all_families() -> None:
    assert set(FAMILY_DOCS) == {
        "EAC1xxx",
        "EAC2xxx",
        "EAC3xxx",
        "EAC4xxx",
        "EAC5xxx",
        "EAC6xxx",
        "EAC7xxx",
        "EAC8xxx",
        "EAC9xxx",
    }


def test_every_catalog_code_is_documented() -> None:
    for code, definition in DIAGNOSTIC_CATALOG.items():
        assert code == definition.code
        assert definition.documentation.strip()
        assert definition.summary_template.strip()
        require_documented(code)


def test_require_documented_rejects_unknown() -> None:
    with pytest.raises(KeyError, match="EAC1999"):
        require_documented("EAC1999")


def test_make_diagnostic_formats_template() -> None:
    diag = make_diagnostic("EAC9001", command="diff")
    assert diag.code == "EAC9001"
    assert diag.severity is Severity.ERROR
    assert "diff" in diag.summary
    assert diag.suggested_repair


def test_diagnostic_code_pattern() -> None:
    with pytest.raises(ValidationError):
        Diagnostic(code="EAC0001", severity=Severity.ERROR, summary="bad family zero")


def test_report_has_errors() -> None:
    report = DiagnosticReport()
    assert not report.has_errors()
    report.add(make_diagnostic("EAC9004"))
    assert not report.has_errors()
    report.add(make_diagnostic("EAC9001", command="lint"))
    assert report.has_errors()
    assert report.highest_severity() is Severity.ERROR


def test_format_diagnostic_includes_repair() -> None:
    diag = make_diagnostic("EAC8001", path="eac.toml", subject="/tmp/ws")
    text = format_diagnostic(diag)
    assert "EAC8001" in text
    assert "repair:" in text
    assert format_report(DiagnosticReport(diagnostics=[diag]))


def test_get_definition() -> None:
    definition = get_definition("EAC1001")
    assert definition.family == "EAC1xxx"
