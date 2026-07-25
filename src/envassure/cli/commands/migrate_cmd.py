"""`eac migrate` - explicit IR schema upgrades (never silent on verify)."""

from __future__ import annotations

from pathlib import Path

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.ir.migrate import migrate_world_document
from envassure.ir.primitives import IR_VERSION


def migrate_command(
    ir_path: Path = typer.Argument(..., help="World IR JSON to migrate."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write migrated IR here (default: overwrite input).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate migration path without writing.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Explicitly upgrade an IR document to the current schema version."""
    result = migrate_world_document(ir_path, output=output, dry_run=dry_run)
    if result.report.has_errors():
        emit_report(result.report, as_json=as_json, exit_code=ExitCode.ERROR)
    emit_success(
        as_json=as_json,
        message=(
            f"IR already at {IR_VERSION}"
            if not result.changed
            else f"Migrated IR {result.from_version} -> {result.to_version}"
        ),
        report=result.report,
        extra={
            "changed": result.changed,
            "from_version": result.from_version,
            "to_version": result.to_version,
            "dry_run": dry_run,
            "notes": result.notes,
            "output": str(output or ir_path) if result.changed and not dry_run else None,
        },
    )
