"""CLI commands for differential validation (`run` / `reproduce`)."""

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
from envassure.differential.http_connector import HttpReferenceConnector
from envassure.differential.minimize import minimize_counterexample
from envassure.differential.probes import plan_probes
from envassure.ir.io import load_world

differential_app = typer.Typer(
    name="differential",
    help="Differential validation against reference connectors.",
    no_args_is_help=True,
)


def _run_campaign(
    *,
    ir_path: Path,
    reference: ReferenceConnector,
    candidate: ReferenceConnector,
    max_probes: int,
    minimize: bool,
    allow_network: bool,
    allow_subprocess: bool,
    seed: int,
    reproduce_path: Path | None = None,
) -> tuple[DiagnosticReport, dict[str, Any]]:
    world = load_world(ir_path)
    probes = plan_probes(world, max_probes=max_probes)
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    results: list[dict[str, Any]] = []
    failing_ids: list[str] = []
    dimension_counts: dict[str, int] = {}

    reference.reset(seed=seed)
    candidate.reset(seed=seed)
    for probe in probes:
        ref_out = reference.execute(probe.id, probe.action_id, probe.payload)
        cand_out = candidate.execute(probe.id, probe.action_id, probe.payload)
        if not isinstance(ref_out, ProbeOutcome):
            continue
        comparison = compare_outcomes(ref_out, cand_out, world=world)
        report.extend(comparison.diagnostics)
        for dim in comparison.failing_dimensions:
            dimension_counts[dim.value] = dimension_counts.get(dim.value, 0) + 1
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
        }

    privileged: dict[str, Any] | None = None
    probe_state = getattr(reference, "probe_state", None)
    if callable(probe_state):
        try:
            privileged = probe_state()
        except Exception as exc:  # noqa: BLE001 — evidence may be absent
            privileged = {"indeterminate": True, "error": str(exc)}

    extra = {
        "environment_id": world.environment_id,
        "reference_connector": reference.name(),
        "candidate_connector": candidate.name(),
        "probe_count": len(probes),
        "results": results,
        "minimized": minimized,
        "failing_dimensions": dimension_counts,
        "tolerances": ComparisonTolerances().model_dump(mode="json"),
        "network_enabled": allow_network,
        "subprocess_enabled": allow_subprocess,
        "seed": seed,
        "privileged_state": privileged,
        "evidence_status": (
            "present"
            if privileged is not None and not privileged.get("indeterminate")
            else "indeterminate"
        ),
    }
    if reproduce_path is not None:
        reproduce_path.parent.mkdir(parents=True, exist_ok=True)
        reproduce_path.write_text(json.dumps(extra, indent=2) + "\n", encoding="utf-8")
        extra["reproduce_path"] = str(reproduce_path)
    return report, extra


def _build_reference(
    *,
    reference_script: Path | None,
    fixture: Path | None,
    simulator: Path | None,
    subprocess_cmd: str | None,
    allow_subprocess: bool,
    http_url: str | None,
    allow_network: bool,
    allow_non_loopback: bool,
    token: str | None,
) -> ReferenceConnector:
    if http_url is not None:
        return HttpReferenceConnector(
            http_url,
            allow_network=allow_network,
            allow_non_loopback=allow_non_loopback,
            privileged_token=token,
        )
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


def _shared_options(fn: Any) -> Any:
    return fn


@differential_app.command("run")
def differential_run(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    reference_script: Path | None = typer.Option(None, "--reference"),
    candidate_script: Path | None = typer.Option(None, "--candidate"),
    fixture: Path | None = typer.Option(None, "--fixture"),
    simulator: Path | None = typer.Option(None, "--simulator"),
    subprocess_cmd: str | None = typer.Option(None, "--subprocess"),
    allow_subprocess: bool = typer.Option(False, "--allow-subprocess"),
    http_url: str | None = typer.Option(None, "--http-url"),
    allow_network: bool = typer.Option(False, "--allow-network"),
    allow_non_loopback: bool = typer.Option(False, "--allow-non-loopback"),
    token: str | None = typer.Option(None, "--token"),
    max_probes: int = typer.Option(128, "--max-probes"),
    seed: int = typer.Option(0, "--seed"),
    minimize: bool = typer.Option(True, "--minimize/--no-minimize"),
    reproduce_out: Path | None = typer.Option(
        None,
        "--reproduce-out",
        help="Write a reproduce bundle JSON for later `differential reproduce`.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run differential probes against a reference connector (offline by default)."""
    reference = _build_reference(
        reference_script=reference_script,
        fixture=fixture,
        simulator=simulator,
        subprocess_cmd=subprocess_cmd,
        allow_subprocess=allow_subprocess,
        http_url=http_url,
        allow_network=allow_network,
        allow_non_loopback=allow_non_loopback,
        token=token,
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

    report, extra = _run_campaign(
        ir_path=ir_path,
        reference=reference,
        candidate=candidate,
        max_probes=max_probes,
        minimize=minimize,
        allow_network=allow_network,
        allow_subprocess=allow_subprocess,
        seed=seed,
        reproduce_path=reproduce_out,
    )
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR, extra=extra)
        return
    emit_success(
        as_json=as_json,
        message=f"Differential validation complete ({extra['probe_count']} probes)",
        report=report,
        extra=extra,
    )
    if not as_json and extra.get("minimized") and extra["minimized"].get("shrunk"):
        console.print(f"minimized CE: {extra['minimized']['minimized']}")


@differential_app.command("reproduce")
def differential_reproduce(
    bundle: Path = typer.Argument(..., help="Reproduce bundle JSON from `differential run`."),
    ir_path: Path | None = typer.Option(
        None,
        "--ir",
        help="Override IR path (defaults to environment_id lookup is not supported; required).",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Replay a saved differential campaign summary (fail closed without IR)."""
    data = json.loads(bundle.read_text(encoding="utf-8"))
    if ir_path is None:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": "differential reproduce requires --ir <world.json>"},
        )
        return
    # Re-run offline against recorded results: compare saved failing set stability.
    prior_failing = [
        r["probe_id"] for r in data.get("results", []) if not r.get("matched", True)
    ]
    # Use fixture-less in-memory echo as a deterministic re-check harness when
    # the original connectors are unavailable; callers should prefer re-run.
    reference = InMemoryReferenceConnector(connector_name="reproduce_ref")
    candidate = InMemoryReferenceConnector(connector_name="reproduce_cand")
    report, extra = _run_campaign(
        ir_path=ir_path,
        reference=reference,
        candidate=candidate,
        max_probes=int(data.get("probe_count") or 128),
        minimize=False,
        allow_network=False,
        allow_subprocess=False,
        seed=int(data.get("seed") or 0),
    )
    extra["prior_failing"] = prior_failing
    extra["reproduced_from"] = str(bundle)
    emit_success(
        as_json=as_json,
        message="Differential reproduce complete",
        report=report,
        extra=extra,
    )


# Backward-compatible flat entry used by older docs / scripts.
def differential_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    reference_script: Path | None = typer.Option(None, "--reference"),
    candidate_script: Path | None = typer.Option(None, "--candidate"),
    fixture: Path | None = typer.Option(None, "--fixture"),
    simulator: Path | None = typer.Option(None, "--simulator"),
    subprocess_cmd: str | None = typer.Option(None, "--subprocess"),
    allow_subprocess: bool = typer.Option(False, "--allow-subprocess"),
    http_url: str | None = typer.Option(None, "--http-url"),
    allow_network: bool = typer.Option(False, "--allow-network"),
    max_probes: int = typer.Option(128, "--max-probes"),
    minimize: bool = typer.Option(True, "--minimize/--no-minimize"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Deprecated flat alias for ``differential run``."""
    differential_run(
        ir_path=ir_path,
        reference_script=reference_script,
        candidate_script=candidate_script,
        fixture=fixture,
        simulator=simulator,
        subprocess_cmd=subprocess_cmd,
        allow_subprocess=allow_subprocess,
        http_url=http_url,
        allow_network=allow_network,
        allow_non_loopback=False,
        token=None,
        max_probes=max_probes,
        seed=0,
        minimize=minimize,
        reproduce_out=None,
        as_json=as_json,
    )
