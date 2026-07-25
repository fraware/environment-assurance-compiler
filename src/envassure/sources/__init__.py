"""Source adapters for deterministic import (Phase 2)."""

from __future__ import annotations

from pathlib import Path

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import SemanticFact
from envassure.sources.base import AdapterResult, SourceAdapter, SourceParseError
from envassure.sources.database import DatabaseAdapter
from envassure.sources.openapi import OpenAPIAdapter
from envassure.sources.policy import PolicyAdapter
from envassure.sources.procedure import ProcedureAdapter
from envassure.sources.traces import TraceAdapter

ADAPTERS: dict[str, SourceAdapter] = {
    OpenAPIAdapter.kind: OpenAPIAdapter(),
    DatabaseAdapter.kind: DatabaseAdapter(),
    PolicyAdapter.kind: PolicyAdapter(),
    ProcedureAdapter.kind: ProcedureAdapter(),
    TraceAdapter.kind: TraceAdapter(),
}

# Aliases for ergonomics / sources.yml kind values.
KIND_ALIASES: dict[str, str] = {
    "openapi": "openapi",
    "api": "openapi",
    "openapi.yaml": "openapi",
    "database": "database",
    "sql": "database",
    "ddl": "database",
    "postgres": "postgres",
    "postgresql": "postgres",
    "pg": "postgres",
    "policy": "policy",
    "procedure": "procedure",
    "sop": "procedure",
    "markdown": "procedure",
    "traces": "traces",
    "trace": "traces",
    "jsonl": "traces",
}


def resolve_kind(kind: str) -> str:
    key = kind.strip().lower()
    if key in KIND_ALIASES:
        return KIND_ALIASES[key]
    if key in ADAPTERS or key == "postgres":
        return key
    raise KeyError(kind)


def get_adapter(kind: str) -> SourceAdapter:
    resolved = resolve_kind(kind)
    if resolved == "postgres":
        from envassure.postgres import PostgresDDLAdapter

        return PostgresDDLAdapter()
    return ADAPTERS[resolved]


def import_source(kind: str, path: Path | str) -> list[SemanticFact]:
    """Parse a source file with the adapter registered for ``kind``.

    Raises:
        SourceParseError: adapter failed closed on bad input.
        KeyError: unknown adapter kind.
    """
    return import_source_detailed(kind, path).facts


def import_source_detailed(kind: str, path: Path | str) -> AdapterResult:
    """Parse a source and return facts plus adapter diagnostics."""
    target = Path(path)
    try:
        adapter = get_adapter(kind)
    except KeyError as exc:
        raise KeyError(f"unknown source adapter kind: {kind}") from exc
    parse_detailed = getattr(adapter, "parse_detailed", None)
    if callable(parse_detailed):
        result = parse_detailed(target)
        if isinstance(result, AdapterResult):
            return result
    return AdapterResult(facts=adapter.parse(target))


def import_source_report(
    kind: str,
    path: Path | str,
) -> tuple[list[SemanticFact], DiagnosticReport]:
    """Import with a DiagnosticReport instead of raising for known failures."""
    report = DiagnosticReport()
    target = Path(path)
    try:
        result = import_source_detailed(kind, target)
        report.extend(result.diagnostics.diagnostics)
        return result.facts, report
    except KeyError:
        report.add(make_diagnostic("EAC1005", kind=kind, subject=kind))
        return [], report
    except ImportError as exc:
        extra = (
            "postgres"
            if "postgres" in str(exc).lower() or "psycopg" in str(exc).lower()
            else "unknown"
        )
        report.add(make_diagnostic("EAC9003", extra=extra, subject=str(target)))
        report.add(
            make_diagnostic(
                "EAC1004",
                path=str(target),
                reason=str(exc),
                subject=str(target),
            )
        )
        return [], report
    except SourceParseError as exc:
        report.add(
            make_diagnostic(
                "EAC1004",
                path=exc.path,
                reason=exc.reason,
                subject=exc.path,
            )
        )
        return [], report


__all__ = [
    "ADAPTERS",
    "KIND_ALIASES",
    "AdapterResult",
    "DatabaseAdapter",
    "OpenAPIAdapter",
    "PolicyAdapter",
    "ProcedureAdapter",
    "SourceAdapter",
    "SourceParseError",
    "TraceAdapter",
    "get_adapter",
    "import_source",
    "import_source_detailed",
    "import_source_report",
    "resolve_kind",
]
