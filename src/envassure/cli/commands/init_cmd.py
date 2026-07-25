"""`eac init` — create an authoring workspace."""

from __future__ import annotations

from pathlib import Path

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.workspace.init import init_workspace


def init_command(
    path: Path | None = typer.Argument(
        None,
        help="Directory to create (default: current directory).",
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        "-n",
        help="Project name (default: directory name).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite eac.toml if present (destructive).",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON.",
    ),
) -> None:
    """Create an EnvAssure workspace tree."""
    target = (path or Path.cwd()).resolve()
    result = init_workspace(target, name=name, force=force)
    if result.report.has_errors():
        emit_report(
            result.report,
            as_json=as_json,
            exit_code=ExitCode.WORKSPACE,
            extra={"path": str(result.paths.root), "created": result.created},
        )
    emit_success(
        as_json=as_json,
        message=f"Initialized EnvAssure workspace at {result.paths.root}",
        extra={
            "path": str(result.paths.root),
            "created": result.created,
        },
    )
