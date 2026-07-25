"""Inspect workspace / IR summaries."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from envassure.cli.output import console, emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.io import load_world
from envassure.workspace.layout import WorkspacePaths
from envassure.workspace.sources import load_sources_manifest


def inspect_command(
    path: Path = typer.Argument(
        Path.cwd(),
        help="Workspace root or IR JSON file.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Summarize a workspace or IR document."""
    target = path.resolve()
    report = DiagnosticReport()
    summary: dict[str, object]

    if target.is_file() and target.suffix == ".json":
        world = load_world(target)
        summary = {
            "kind": "ir",
            "environment_id": world.environment_id,
            "name": world.name,
            "version": world.version,
            "counts": {
                "state": len(world.state),
                "actors": len(world.actors),
                "actions": len(world.actions),
                "transitions": len(world.transitions),
                "tasks": len(world.tasks),
                "verifiers": len(world.verifiers),
                "ambiguities": len(world.ambiguities),
            },
        }
    else:
        paths = WorkspacePaths(root=target)
        missing = paths.missing_required()
        if missing:
            for item in missing:
                report.add(make_diagnostic("EAC8001", path=item, subject=str(target)))
            emit_report(report, as_json=as_json, exit_code=ExitCode.WORKSPACE)
        manifest = load_sources_manifest(paths.sources_yml)
        ir_path = paths.ir_dir / "world.json"
        ir_summary = None
        if ir_path.is_file():
            world = load_world(ir_path)
            ir_summary = {
                "environment_id": world.environment_id,
                "actions": len(world.actions),
                "ambiguities_open": sum(1 for a in world.ambiguities if a.status == "open"),
            }
        summary = {
            "kind": "workspace",
            "path": str(paths.root),
            "sources": len(manifest.sources),
            "ir": ir_summary,
        }

    if as_json:
        console.print_json(json.dumps({"ok": True, "exit_code": 0, "summary": summary}))
    else:
        emit_success(as_json=False, message="Inspect summary", extra={"summary": summary})
