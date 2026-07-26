"""Compiler diagnostics (EAC1xxx-EAC9xxx)."""

from __future__ import annotations

from envassure.diagnostics.catalog import (
    DIAGNOSTIC_CATALOG,
    DiagnosticDefinition,
    catalog_semantic_fingerprint,
    get_definition,
    iter_catalog,
    require_documented,
)
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.models import (
    Diagnostic,
    DiagnosticReport,
    Severity,
    SourceRef,
)
from envassure.diagnostics.render import format_diagnostic, format_report

__all__ = [
    "DIAGNOSTIC_CATALOG",
    "Diagnostic",
    "DiagnosticDefinition",
    "DiagnosticReport",
    "ExitCode",
    "Severity",
    "SourceRef",
    "catalog_semantic_fingerprint",
    "format_diagnostic",
    "format_report",
    "get_definition",
    "iter_catalog",
    "require_documented",
]
