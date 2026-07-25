"""CLI commands for static analysis and coverage."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from envassure.analysis.coverage import CoverageTrace, compute_coverage
from envassure.analysis.static import analyze_world
from envassure.cli.output import console, emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.ir.io import load_world
from envassure.verifiers import audit_verifiers


def analyze_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    bound: int = typer.Option(64, "--bound", help="BFS depth bound for reachability."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run static assurance analyses on a WorldDefinition."""
    world = load_world(ir_path)
    result = analyze_world(world, bfs_bound=bound)
    result.report.extend(audit_verifiers(world).diagnostics)
    extra = {
        "environment_id": world.environment_id,
        "reachable_actions": sorted(result.reachability.reachable_actions),
        "mutation_scopes": [
            {
                "action_id": s.action_id,
                "writes": s.writes,
                "mutation_authority": s.mutation_authority,
            }
            for s in result.mutation_scopes
        ],
        "details": result.details,
    }
    if result.report.has_errors():
        emit_report(
            result.report,
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra=extra,
        )
    emit_success(
        as_json=as_json,
        message=f"Analysis complete for {world.environment_id}",
        report=result.report,
        extra=extra,
    )


def coverage_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    trace: Path | None = typer.Option(
        None,
        "--trace",
        help="Optional CoverageTrace JSON (actions/transitions/failures/observations).",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Report multi-dimensional coverage against IR declarations."""
    world = load_world(ir_path)
    coverage_trace: CoverageTrace | None = None
    if trace is not None:
        coverage_trace = CoverageTrace.model_validate(json.loads(trace.read_text(encoding="utf-8")))
    report = compute_coverage(world, coverage_trace)
    payload = report.as_dict()
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "ok": True,
                    "exit_code": 0,
                    "environment_id": world.environment_id,
                    "coverage": payload,
                    "notes": report.notes,
                    "complete": report.overall_complete(),
                }
            )
        )
    else:
        console.print(f"Coverage for {world.environment_id}")
        for name, dim in payload.items():
            console.print(
                f"- {name}: {dim['ratio']:.0%} "
                f"({len(dim['covered'])}/{dim['total']}); "
                f"missing={dim['missing']}"
            )
        for note in report.notes:
            console.print(f"note: {note}")
