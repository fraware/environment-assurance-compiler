"""`eac doctor` — toolchain and workspace health checks."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.table import Table

from envassure.cli.output import console, emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.workspace.doctor import run_doctor
from envassure.workspace.layout import WorkspacePaths


def doctor_command(
    path: Path | None = typer.Option(
        None,
        "--path",
        "-p",
        help="Workspace root (default: cwd if it is a workspace).",
    ),
    network: bool = typer.Option(
        False,
        "--network",
        help="Opt in to network checks (none registered in Phase 0).",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Check Python, optional extras, and lock consistency."""
    root: Path | None
    if path is not None:
        root = path.resolve()
    else:
        cwd = Path.cwd().resolve()
        root = cwd if WorkspacePaths(root=cwd).is_workspace() else None

    result = run_doctor(root, network=network)
    checks_payload = [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in result.checks]

    if not as_json:
        table = Table(title="eac doctor")
        table.add_column("Check")
        table.add_column("OK")
        table.add_column("Detail")
        for check in result.checks:
            table.add_row(check.name, "yes" if check.ok else "no", check.detail)
        console.print(table)

    if not result.ok:
        code = ExitCode.DOCTOR
        if any(d.code.startswith("EAC8") for d in result.report.errors()):
            code = ExitCode.WORKSPACE
        emit_report(
            result.report,
            as_json=as_json,
            exit_code=code,
            extra={"checks": checks_payload, "network": network},
        )

    emit_success(
        as_json=as_json,
        message="Doctor checks passed.",
        report=result.report,
        extra={"checks": checks_payload, "network": network},
    )
