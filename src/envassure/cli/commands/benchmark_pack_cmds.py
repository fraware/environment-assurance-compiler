"""CLI group ``eac pack`` for research benchmark packs (not Environment Packs).

Existing ``eac package`` / ``eac verify-pack`` continue to manage ``.eap`` archives.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from envassure.benchmark.pack_format import (
    discover_benchmark_packs,
    inspect_benchmark_pack,
    lint_benchmark_pack,
    load_pack_manifest,
    reproduce_benchmark_pack,
    summarize_pack_paths,
    verify_benchmark_pack,
)
from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport

pack_app = typer.Typer(
    name="pack",
    help=(
        "Research benchmark packs (pack.yaml): lint / verify / reproduce / inspect. "
        "Distinct from `eac package` / `verify-pack` for Environment Packs (.eap)."
    ),
    no_args_is_help=True,
)


def _resolve_targets(path: Path) -> list[Path]:
    path = path.resolve()
    if (path / "pack.yaml").is_file():
        return [path]
    discovered = discover_benchmark_packs(path)
    if discovered:
        return discovered
    return [path]


@pack_app.command("lint")
def pack_lint(
    path: Path = typer.Argument(
        Path("packs"),
        help="Pack directory or parent containing pack.yaml children.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Lint benchmark pack layout and pack.yaml schema."""
    targets = _resolve_targets(path)
    combined = DiagnosticReport(diagnostics=[])
    results: list[dict[str, object]] = []
    for target in targets:
        report = lint_benchmark_pack(target)
        combined.diagnostics.extend(report.diagnostics)
        results.append(
            {
                "path": str(target),
                "ok": not report.has_errors(),
                "diagnostic_count": len(report.diagnostics),
            }
        )
    if combined.has_errors():
        emit_report(
            combined,
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"packs": results},
        )
    emit_success(
        as_json=as_json,
        message=f"linted {len(targets)} benchmark pack(s)",
        extra={"packs": results},
        report=combined,
    )


@pack_app.command("verify")
def pack_verify(
    path: Path = typer.Argument(
        Path("packs"),
        help="Pack directory or parent containing pack.yaml children.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Verify digests, baseline IR, and secret scan for benchmark packs."""
    targets = _resolve_targets(path)
    combined = DiagnosticReport(diagnostics=[])
    results: list[dict[str, object]] = []
    for target in targets:
        report = verify_benchmark_pack(target)
        combined.diagnostics.extend(report.diagnostics)
        pack_id = None
        try:
            pack_id = load_pack_manifest(target / "pack.yaml").pack_id
        except (OSError, ValueError, TypeError, ValidationError, yaml.YAMLError):
            pack_id = None
        results.append(
            {
                "path": str(target),
                "pack_id": pack_id,
                "ok": not report.has_errors(),
                "diagnostic_count": len(report.diagnostics),
            }
        )
    if combined.has_errors():
        emit_report(
            combined,
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"packs": results},
        )
    emit_success(
        as_json=as_json,
        message=f"verified {len(targets)} benchmark pack(s)",
        extra={"packs": results},
        report=combined,
    )


@pack_app.command("inspect")
def pack_inspect(
    path: Path = typer.Argument(..., help="Pack directory containing pack.yaml."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect a single benchmark pack manifest and public digest."""
    path = path.resolve()
    try:
        report = inspect_benchmark_pack(path)
    except ValueError as exc:
        emit_report(
            DiagnosticReport(
                diagnostics=[
                    make_diagnostic(
                        "EAC8006",
                        reason=str(exc),
                        subject=str(path),
                    )
                ]
            ),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
        )
    payload = report.model_dump(mode="json")
    emit_success(
        as_json=as_json,
        message=f"{report.manifest.pack_id}@{report.manifest.version}",
        extra={"inspect": payload},
    )


@pack_app.command("reproduce")
def pack_reproduce(
    path: Path = typer.Argument(..., help="Pack directory containing pack.yaml."),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional directory for the reproduce receipt JSON.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Verify the pack contract and write a reproduce receipt."""
    path = path.resolve()
    try:
        receipt = reproduce_benchmark_pack(path, output_dir=output)
    except ValueError as exc:
        emit_report(
            DiagnosticReport(
                diagnostics=[
                    make_diagnostic(
                        "EAC8006",
                        reason=str(exc),
                        subject=str(path),
                    )
                ]
            ),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
        )
    emit_success(
        as_json=as_json,
        message=f"reproduced contract for {receipt['pack_id']}",
        extra={"receipt": receipt},
    )


@pack_app.command("list")
def pack_list(
    path: Path = typer.Argument(
        Path("packs"),
        help="Parent directory to scan for pack.yaml children.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List discovered benchmark packs under a directory."""
    rows = summarize_pack_paths(discover_benchmark_packs(path))
    emit_success(
        as_json=as_json,
        message=f"{len(rows)} pack(s)",
        extra={"packs": rows},
    )
