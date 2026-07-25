"""CLI commands for import, facts, ambiguities, and decide (Phase 2)."""

from __future__ import annotations

from pathlib import Path

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.store import FactStore
from envassure.reconciliation import reconcile
from envassure.review import (
    apply_decision,
    list_ambiguities,
    load_ambiguities,
    save_ambiguities,
    save_decision_under,
)
from envassure.sources import import_source_report
from envassure.workspace.config import load_workspace_config
from envassure.workspace.layout import WorkspacePaths


def import_command(
    kind: str = typer.Argument(..., help="Adapter kind: openapi|database|policy|procedure|traces"),
    source: Path = typer.Argument(..., help="Path to the source artifact."),
    path: Path = typer.Option(
        Path.cwd(),
        "--path",
        "-p",
        help="Workspace root (facts written under facts/).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Facts JSON path (default: <workspace>/facts/imported.json).",
    ),
    merge: bool = typer.Option(
        False,
        "--merge",
        help="Merge into an existing facts file instead of replacing it.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Import a source artifact into SemanticFact candidates."""
    facts, report = import_source_report(kind, source)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    out = output
    if out is None:
        paths = WorkspacePaths(root=path.resolve())
        out = paths.facts_dir / "imported.json"

    if merge and out.is_file():
        store = FactStore.load(out)
        store.extend(facts, overwrite=True)
    else:
        store = FactStore(facts)
    store.save(out)
    emit_success(
        as_json=as_json,
        message=f"Imported {len(facts)} facts from {source}"
        + (f" (store now {len(store)})" if merge else ""),
        report=report,
        extra={
            "output": str(out),
            "fact_count": len(store),
            "imported_count": len(facts),
            "kind": kind,
            "merged": merge,
        },
    )


def facts_command(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Workspace root."),
    facts_file: Path | None = typer.Option(
        None,
        "--facts",
        "-f",
        help="Facts JSON path (default: <workspace>/facts/imported.json).",
    ),
    reconcile_facts: bool = typer.Option(
        False,
        "--reconcile",
        help="Run reconciliation and write ambiguities.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List stored facts; optionally reconcile into ambiguities."""
    paths = WorkspacePaths(root=path.resolve())
    target = facts_file or (paths.facts_dir / "imported.json")
    report = DiagnosticReport()
    if not target.is_file():
        report.add(
            make_diagnostic(
                "EAC8001",
                path=str(target),
                subject=str(target),
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.WORKSPACE)

    store = FactStore.load(target)
    extra: dict[str, object] = {
        "fact_count": len(store),
        "facts": [f.model_dump(mode="json") for f in store.list()],
    }
    if reconcile_facts:
        precedence = None
        if paths.eac_toml.is_file():
            precedence = load_workspace_config(paths.eac_toml).source_precedence
        result = reconcile(store.list(), precedence)
        report.extend(result.diagnostics.diagnostics)
        amb_path = paths.facts_dir / "ambiguities.json"
        save_ambiguities(amb_path, result.ambiguities)
        extra["ambiguity_count"] = len(result.ambiguities)
        extra["ambiguities"] = [a.model_dump(mode="json") for a in result.ambiguities]
        extra["ambiguities_path"] = str(amb_path)
        if report.has_errors():
            emit_report(
                report,
                as_json=as_json,
                exit_code=ExitCode.ERROR,
                extra=extra,
            )
    emit_success(
        as_json=as_json,
        message=f"{len(store)} facts in {target}",
        report=report,
        extra=extra,
    )


def ambiguities_command(
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Workspace root."),
    ambiguities_file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Ambiguities JSON (default: <workspace>/facts/ambiguities.json).",
    ),
    status: str | None = typer.Option(
        "open",
        "--status",
        help="Filter by status (open|accepted|deferred|rejected); omit with empty for all.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List ambiguity records."""
    paths = WorkspacePaths(root=path.resolve())
    target = ambiguities_file or (paths.facts_dir / "ambiguities.json")
    report = DiagnosticReport()
    if not target.is_file():
        report.add(
            make_diagnostic(
                "EAC8001",
                path=str(target),
                subject=str(target),
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.WORKSPACE)

    all_amb = load_ambiguities(target)
    filter_status: str | None = None if status in {None, "", "all"} else status
    filtered = list_ambiguities(
        all_amb,
        status=filter_status,  # type: ignore[arg-type]
    )
    # Surface open ambiguities as EAC2001 warnings for visibility.
    for amb in filtered:
        if amb.status == "open":
            report.add(
                make_diagnostic(
                    "EAC2001",
                    ambiguity_id=amb.id,
                    subject=amb.subject,
                )
            )
    emit_success(
        as_json=as_json,
        message=f"{len(filtered)} ambiguities ({filter_status or 'all'})",
        report=report,
        extra={
            "count": len(filtered),
            "ambiguities": [a.model_dump(mode="json") for a in filtered],
        },
    )


def decide_command(
    ambiguity_id: str = typer.Argument(..., help="Ambiguity id to resolve."),
    interpretation: str = typer.Option(
        ...,
        "--interpretation",
        "-i",
        help="Chosen interpretation text.",
    ),
    role: str = typer.Option(
        ...,
        "--role",
        "-r",
        help="Expert role recording the decision.",
    ),
    rationale: str = typer.Option(
        ...,
        "--rationale",
        help="Rationale for the decision.",
    ),
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Workspace root."),
    ambiguities_file: Path | None = typer.Option(
        None,
        "--file",
        "-f",
        help="Ambiguities JSON path.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Record an expert decision and update ambiguity status."""
    paths = WorkspacePaths(root=path.resolve())
    target = ambiguities_file or (paths.facts_dir / "ambiguities.json")
    report = DiagnosticReport()
    if not target.is_file():
        report.add(
            make_diagnostic(
                "EAC8001",
                path=str(target),
                subject=str(target),
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.WORKSPACE)

    ambiguities = load_ambiguities(target)
    result = apply_decision(
        ambiguities,
        ambiguity_id=ambiguity_id,
        chosen_interpretation=interpretation,
        expert_role=role,
        rationale=rationale,
    )
    report.extend(result.diagnostics.diagnostics)
    if report.has_errors() or result.decision is None:
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    assert result.decision is not None
    save_ambiguities(target, result.ambiguities)
    decision_path = save_decision_under(paths.decisions_dir, result.decision)
    emit_success(
        as_json=as_json,
        message=f"Decision {result.decision.decision_id} recorded for {ambiguity_id}",
        report=report,
        extra={
            "decision": result.decision.model_dump(mode="json"),
            "decision_path": str(decision_path),
            "ambiguities_path": str(target),
        },
    )
