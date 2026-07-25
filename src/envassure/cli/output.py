"""Shared CLI output helpers (human + --json)."""

from __future__ import annotations

import json
import sys
from typing import Any, NoReturn

import typer
from rich.console import Console

from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.models import Diagnostic, DiagnosticReport
from envassure.diagnostics.render import format_report

console = Console(stderr=False)
err_console = Console(stderr=True)


def emit_report(
    report: DiagnosticReport,
    *,
    as_json: bool,
    exit_code: ExitCode,
    extra: dict[str, Any] | None = None,
) -> NoReturn:
    """Print diagnostics and exit with a stable code."""
    payload: dict[str, Any] = {
        "ok": exit_code is ExitCode.SUCCESS,
        "exit_code": int(exit_code),
        "diagnostics": [d.model_dump(mode="json") for d in report.diagnostics],
    }
    if extra:
        payload.update(extra)
    if as_json:
        console.print_json(json.dumps(payload))
    else:
        text = format_report(report)
        if report.diagnostics:
            err_console.print(text)
        if extra:
            for key, value in extra.items():
                if key in {"ok", "exit_code", "diagnostics"}:
                    continue
                console.print(f"{key}: {value}")
    raise typer.Exit(code=int(exit_code))


def emit_success(
    *,
    as_json: bool,
    message: str,
    extra: dict[str, Any] | None = None,
    report: DiagnosticReport | None = None,
) -> None:
    diagnostics = report.diagnostics if report is not None else []
    payload: dict[str, Any] = {
        "ok": True,
        "exit_code": int(ExitCode.SUCCESS),
        "message": message,
        "diagnostics": [d.model_dump(mode="json") for d in diagnostics],
    }
    if extra:
        payload.update(extra)
    if as_json:
        console.print_json(json.dumps(payload))
    else:
        console.print(message)
        if diagnostics:
            err_console.print(format_report(DiagnosticReport(diagnostics=diagnostics)))
        if extra:
            for key, value in extra.items():
                if key in {"ok", "exit_code", "message", "diagnostics"}:
                    continue
                console.print(f"{key}: {value}")


def fail_unimplemented(command: str, *, as_json: bool) -> NoReturn:
    from envassure.diagnostics.factory import make_diagnostic

    report = DiagnosticReport()
    report.add(make_diagnostic("EAC9001", command=command, subject=command))
    emit_report(report, as_json=as_json, exit_code=ExitCode.UNIMPLEMENTED)


def dump_diagnostic(diagnostic: Diagnostic) -> dict[str, Any]:
    return diagnostic.model_dump(mode="json")


def configure_traceback(show: bool) -> None:
    if not show:
        sys.tracebacklimit = 0
