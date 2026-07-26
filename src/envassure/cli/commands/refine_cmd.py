"""CLI: counterexample-guided reconciliation (`eac refine`)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import SemanticFact
from envassure.reconciliation.cegr import (
    apply_cegr,
    counterexample_from_mapping,
    run_cegr_loop,
)


def refine_command(
    intake: Path = typer.Argument(
        ...,
        help="Counterexample intake JSON (stable CEGR schema or differential export).",
    ),
    workspace: Path = typer.Option(
        Path.cwd(),
        "--workspace",
        "-w",
        help="Workspace root for validation/refinements/ persistence.",
    ),
    facts: Path | None = typer.Option(
        None,
        "--facts",
        help="Optional existing facts JSON array to merge before reconcile.",
    ),
    no_persist: bool = typer.Option(
        False,
        "--no-persist",
        help="Compute CEGR result without writing refinement generations.",
    ),
    parent_digest: str | None = typer.Option(
        None,
        "--parent-digest",
        help="Optional parent generation digest for lineage.",
    ),
    loop: bool = typer.Option(
        False,
        "--loop",
        help="Run CEGR v2 loop (minimize metadata, replay hooks, close-on-evidence).",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Apply CEGR: counterexample -> ambiguities / corrected facts / transition patches."""
    report = DiagnosticReport()
    if not intake.is_file():
        report.add(
            make_diagnostic(
                "EAC9005",
                reason=f"intake file not found: {intake}",
                subject=str(intake),
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    raw = json.loads(intake.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        report.add(
            make_diagnostic(
                "EAC9005",
                reason="intake JSON must be an object",
                subject=str(intake),
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    existing: list[SemanticFact] = []
    if facts is not None:
        if not facts.is_file():
            report.add(
                make_diagnostic(
                    "EAC9005",
                    reason=f"facts file not found: {facts}",
                    subject=str(facts),
                )
            )
            emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
        payload = json.loads(facts.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and "facts" in payload:
            payload = payload["facts"]
        existing = [SemanticFact.model_validate(item) for item in payload]

    ce = counterexample_from_mapping(raw)
    if loop:
        loop_result = run_cegr_loop(
            ce,
            existing_facts=existing,
            parent_digest=parent_digest,
            workspace_root=None if no_persist else workspace,
            persist=not no_persist,
        )
        report.extend(loop_result.diagnostics.diagnostics)
        result = loop_result.result
        emit_success(
            as_json=as_json,
            message=(
                f"CEGR v2 loop generation {result.generation.generation} "
                f"(closed={loop_result.closed}, "
                f"{len(result.ambiguities)} ambiguities, "
                f"{len(result.corrected_facts)} facts, "
                f"{len(result.transition_patches)} patches)"
            ),
            report=report,
            extra={
                "generation": result.generation.generation,
                "generation_dir": result.generation_dir,
                "intake_digest": result.intake.content_digest(),
                "closed": loop_result.closed,
                "close_evidence": loop_result.close_evidence,
                "accepted_fact_ids": result.generation.reconciliation.get("accepted_fact_ids", []),
                "ambiguity_ids": [a.id for a in result.ambiguities],
                "corrected_fact_ids": [f.fact_id for f in result.corrected_facts],
                "transition_patches": [
                    p.model_dump(mode="json") for p in result.transition_patches
                ],
                "minimization": loop_result.minimization,
            },
        )
        return

    result = apply_cegr(
        ce,
        existing_facts=existing,
        parent_digest=parent_digest,
        workspace_root=None if no_persist else workspace,
        persist=not no_persist,
    )
    report.extend(result.diagnostics.diagnostics)
    emit_success(
        as_json=as_json,
        message=(
            f"CEGR generation {result.generation.generation} "
            f"({len(result.ambiguities)} ambiguities, "
            f"{len(result.corrected_facts)} facts, "
            f"{len(result.transition_patches)} patches)"
        ),
        report=report,
        extra={
            "generation": result.generation.generation,
            "generation_dir": result.generation_dir,
            "intake_digest": result.intake.content_digest(),
            "accepted_fact_ids": result.generation.reconciliation.get("accepted_fact_ids", []),
            "ambiguity_ids": [a.id for a in result.ambiguities],
            "corrected_fact_ids": [f.fact_id for f in result.corrected_facts],
            "transition_patches": [p.model_dump(mode="json") for p in result.transition_patches],
        },
    )
