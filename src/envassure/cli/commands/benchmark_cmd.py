"""CLI: offline hidden-reference / generator benchmark."""

from __future__ import annotations

from pathlib import Path

import typer

from envassure.benchmark import (
    AblationConfig,
    default_ablations,
    default_beta_suite,
    run_ablation_sweep,
    run_fixture_benchmark,
    write_benchmark_report,
)
from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport


def benchmark_command(
    fixture: Path | None = typer.Argument(
        None,
        help="Fixture oracle JSON path (default: suite fixtures if --suite).",
    ),
    suite: bool = typer.Option(
        False,
        "--suite",
        help="Run default beta suite fixtures relative to repo/CWD.",
    ),
    ablation: bool = typer.Option(
        False,
        "--ablation",
        help="Sweep default ablation configs over the fixture.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write benchmark report JSON.",
    ),
    max_probes: int = typer.Option(100, "--max-probes"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run offline fixture-oracle benchmarks (no network)."""
    report = DiagnosticReport()
    if suite:
        suite_model = default_beta_suite()
        reports = []
        for case in suite_model.cases:
            path = Path(case.fixture_path or "")
            if not path.is_file():
                report.add(
                    make_diagnostic(
                        "EAC9005",
                        reason=f"suite fixture missing: {path}",
                        subject=case.case_id,
                    )
                )
                continue
            abl = AblationConfig(
                name="suite",
                hidden_reference=True,
                max_probes=max_probes,
            )
            reports.append(
                run_fixture_benchmark(
                    path,
                    ablation=abl,
                    case_id=case.case_id,
                    suite_id=suite_model.suite_id,
                    metrics=case.metrics,
                )
            )
        if report.has_errors() and not reports:
            emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
        payload = [r.model_dump(mode="json") for r in reports]
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            import json

            output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        emit_success(
            as_json=as_json,
            message=f"Benchmark suite: {len(reports)} case(s)",
            report=report,
            extra={"reports": payload, "output": str(output) if output else None},
        )
        return

    if fixture is None:
        report.add(
            make_diagnostic(
                "EAC9005",
                reason="provide a fixture path or pass --suite",
                subject="benchmark",
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    if not fixture.is_file():
        report.add(
            make_diagnostic(
                "EAC9005",
                reason=f"fixture not found: {fixture}",
                subject=str(fixture),
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    abl = AblationConfig(name="cli", hidden_reference=True, max_probes=max_probes)
    if ablation:
        results = run_ablation_sweep(fixture, default_ablations(), case_id=fixture.stem)
        payload = [r.model_dump(mode="json") for r in results]
        if output is not None:
            import json

            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        emit_success(
            as_json=as_json,
            message=f"Ablation sweep: {len(results)} config(s)",
            extra={"reports": payload, "output": str(output) if output else None},
        )
        return

    result = run_fixture_benchmark(fixture, ablation=abl, case_id=fixture.stem)
    if output is not None:
        write_benchmark_report(result, output)
    emit_success(
        as_json=as_json,
        message=(
            f"Benchmark {result.case_id}: {result.episode_count} episodes "
            f"(diff_match={result.metrics.diff_match})"
        ),
        extra={
            "report": result.model_dump(mode="json"),
            "output": str(output) if output else None,
        },
    )
