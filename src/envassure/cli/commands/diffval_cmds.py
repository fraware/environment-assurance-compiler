"""CLI command for differential validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from envassure.cli.output import console, emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.models import DiagnosticReport
from envassure.differential.compare import ComparisonTolerances, compare_outcomes
from envassure.differential.connector import (
    FileBackedSimulatorConnector,
    InMemoryReferenceConnector,
    LocalHttpStubConnector,
    ProbeOutcome,
    RecordedFixtureConnector,
    ReferenceConnector,
    SubprocessReferenceConnector,
)
from envassure.differential.minimize import minimize_counterexample
from envassure.differential.probes import plan_probes
from envassure.ir.io import load_world


def differential_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    reference_script: Path | None = typer.Option(
        None,
        "--reference",
        help="JSON map of probe/action keys to ProbeOutcome dicts for InMemoryReferenceConnector.",
    ),
    candidate_script: Path | None = typer.Option(
        None,
        "--candidate",
        help="JSON map for candidate outcomes (defaults to matching reference).",
    ),
    fixture: Path | None = typer.Option(
        None,
        "--fixture",
        help="Recorded fixture JSON for RecordedFixtureConnector (offline replay).",
    ),
    simulator: Path | None = typer.Option(
        None,
        "--simulator",
        help="File-backed simulator definition JSON (offline state machine).",
    ),
    subprocess_cmd: str | None = typer.Option(
        None,
        "--subprocess",
        help="Local subprocess command (JSON stdin/stdout). Requires --allow-subprocess.",
    ),
    allow_subprocess: bool = typer.Option(
        False,
        "--allow-subprocess",
        help="Opt in to SubprocessReferenceConnector (off by default).",
    ),
    http_url: str | None = typer.Option(
        None,
        "--http-url",
        help="Loopback HTTP stub URL (requires --allow-network).",
    ),
    allow_network: bool = typer.Option(
        False,
        "--allow-network",
        help="Opt in to loopback HTTP connector (off by default).",
    ),
    max_probes: int = typer.Option(128, "--max-probes"),
    minimize: bool = typer.Option(
        True,
        "--minimize/--no-minimize",
        help="Minimize failing probe id sequences when mismatches occur.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run differential probes against a reference connector (offline by default)."""
    world = load_world(ir_path)
    reference = _build_reference(
        reference_script=reference_script,
        fixture=fixture,
        simulator=simulator,
        subprocess_cmd=subprocess_cmd,
        allow_subprocess=allow_subprocess,
        http_url=http_url,
        allow_network=allow_network,
    )
    cand_scripts = _load_scripts(candidate_script) if candidate_script else None
    if cand_scripts is not None:
        candidate: ReferenceConnector = InMemoryReferenceConnector(
            connector_name="candidate",
            scripts=cand_scripts,
        )
    elif simulator is not None:
        candidate = FileBackedSimulatorConnector(
            definition_path=simulator,
            connector_name="candidate_sim",
        )
    elif fixture is not None:
        candidate = RecordedFixtureConnector(fixture_path=fixture, connector_name="candidate")
    else:
        candidate = InMemoryReferenceConnector(
            connector_name="candidate",
            scripts=_load_scripts(reference_script),
        )

    probes = plan_probes(world, max_probes=max_probes)
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    results: list[dict[str, Any]] = []
    failing_ids: list[str] = []

    reference.reset(seed=0)
    candidate.reset(seed=0)
    for probe in probes:
        ref_out = reference.execute(probe.id, probe.action_id, probe.payload)
        cand_out = candidate.execute(probe.id, probe.action_id, probe.payload)
        if not isinstance(ref_out, ProbeOutcome):
            continue
        comparison = compare_outcomes(ref_out, cand_out, world=world)
        report.extend(comparison.diagnostics)
        results.append(
            {
                "probe_id": probe.id,
                "kind": probe.kind.value,
                "matched": comparison.matched,
                "failing_dimensions": [d.value for d in comparison.failing_dimensions],
                "dimensions": list(probe.dimensions),
            }
        )
        if not comparison.matched:
            failing_ids.append(probe.id)

    minimized: dict[str, Any] | None = None
    if minimize and failing_ids:
        fail_set = set(failing_ids)

        def fails(seq: list[str]) -> bool:
            return any(item in fail_set for item in seq)

        mini = minimize_counterexample(failing_ids, fails, probe_id="diff.batch")
        report.extend(mini.diagnostics)
        minimized = {
            "original_len": len(mini.original),
            "minimized_len": len(mini.minimized),
            "minimized": mini.minimized,
            "shrunk": mini.shrunk,
            "reduction_steps": [
                {
                    "iteration": step.iteration,
                    "kind": step.kind,
                    "before_len": step.before_len,
                    "after_len": step.after_len,
                    "kept": step.kept,
                }
                for step in mini.reduction_steps
            ],
        }

    extra = {
        "environment_id": world.environment_id,
        "reference_connector": reference.name(),
        "probe_count": len(probes),
        "results": results,
        "minimized": minimized,
        "tolerances": ComparisonTolerances().model_dump(mode="json"),
        "network_enabled": allow_network,
        "subprocess_enabled": allow_subprocess,
    }
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR, extra=extra)
    emit_success(
        as_json=as_json,
        message=f"Differential validation complete ({len(probes)} probes)",
        report=report,
        extra=extra,
    )
    if not as_json and minimized and minimized.get("shrunk"):
        console.print(f"minimized CE: {minimized['minimized']}")


def _build_reference(
    *,
    reference_script: Path | None,
    fixture: Path | None,
    simulator: Path | None,
    subprocess_cmd: str | None,
    allow_subprocess: bool,
    http_url: str | None,
    allow_network: bool,
) -> ReferenceConnector:
    if http_url is not None:
        return LocalHttpStubConnector(http_url, allow_network=allow_network)
    if subprocess_cmd is not None:
        return SubprocessReferenceConnector(
            subprocess_cmd.split(),
            allow_subprocess=allow_subprocess,
        )
    if simulator is not None:
        return FileBackedSimulatorConnector(definition_path=simulator)
    if fixture is not None:
        return RecordedFixtureConnector(fixture_path=fixture)
    return InMemoryReferenceConnector(scripts=_load_scripts(reference_script))


def _load_scripts(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise typer.BadParameter("reference script must be a JSON object")
    return data
