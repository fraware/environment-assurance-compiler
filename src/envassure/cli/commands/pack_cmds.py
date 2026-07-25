"""CLI commands for package, verify-pack, and report."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.io import load_world
from envassure.ir.models import AmbiguityRecord
from envassure.ir.validate import ReleaseProfile, validate_world
from envassure.obligations import compile_proof_obligations, proof_obligation_pack_members
from envassure.packaging import save_pack, verify_pack
from envassure.reports import (
    assurance_pack_members,
    build_assurance_case,
    write_assurance_report,
)


def package_command(
    ir_path: Path = typer.Argument(..., help="World IR JSON."),
    output: Path = typer.Option(Path("pack.eap"), "--output", "-o"),
    include_report: bool = typer.Option(
        True,
        "--include-report/--no-include-report",
        help="Embed assurance-case JSON/HTML in the pack.",
    ),
    profile: str = typer.Option(
        ReleaseProfile.RESEARCH_RELEASE.value,
        "--profile",
        help=(
            "Release profile gate before packing: authoring | executable | "
            "differential | research_release | deployment_calibration."
        ),
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Build an Environment Pack (.eap)."""
    world = load_world(ir_path)
    report = validate_world(world, profile=profile)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    extra: dict[str, bytes | str] = {}
    proof_bundle = compile_proof_obligations(world)
    extra.update(proof_obligation_pack_members(proof_bundle))
    if include_report:
        case = build_assurance_case(
            world,
            ambiguities=list(world.ambiguities),
            proof_obligations=proof_bundle,
        )
        extra.update(assurance_pack_members(case))
    try:
        manifest = save_pack(output, world, extra_files=extra or None)
    except ValueError as exc:
        report.add(make_diagnostic("EAC8006", reason=str(exc), subject=str(output)))
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    emit_success(
        as_json=as_json,
        message=f"Wrote pack {output}",
        report=report,
        extra={
            "output": str(output),
            "content_digest": manifest.content_digest,
            "environment_id": world.environment_id,
            "included_report": include_report,
            "profile": profile,
            "proof_obligation_count": len(proof_bundle.obligations),
        },
    )


def verify_pack_command(
    pack_path: Path = typer.Argument(..., help="Path to .eap pack."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Verify pack checksums and secret scan gates."""
    report = verify_pack(pack_path)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    emit_success(
        as_json=as_json,
        message=f"Pack OK: {pack_path}",
        report=report,
        extra={"pack": str(pack_path)},
    )


def report_command(
    ir_path: Path = typer.Argument(..., help="World IR JSON."),
    output_dir: Path = typer.Option(Path("reports"), "--output", "-o"),
    diagnostics: Path | None = typer.Option(
        None,
        "--diagnostics",
        help="Optional diagnostics JSON (list or {diagnostics: [...]}).",
    ),
    ambiguities: Path | None = typer.Option(
        None,
        "--ambiguities",
        help="Optional ambiguities JSON array.",
    ),
    static_analysis: Path | None = typer.Option(
        None,
        "--static",
        help="Optional static analysis artifact JSON.",
    ),
    dynamic_validation: Path | None = typer.Option(
        None,
        "--dynamic",
        help="Optional dynamic validation artifact JSON.",
    ),
    differential: Path | None = typer.Option(
        None,
        "--differential",
        help="Optional differential validation artifact JSON.",
    ),
    artifacts: Path | None = typer.Option(
        None,
        "--artifacts",
        help="Optional artifact digest map JSON object.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Write section 20 assurance-case JSON + HTML from canonical artifacts only."""
    world = load_world(ir_path)

    def _load_obj(path: Path | None) -> dict[str, object] | list[object] | None:
        if path is None:
            return None
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            return raw
        return None

    diag_raw = _load_obj(diagnostics)
    diag_list: list[dict[str, object]] = []
    if isinstance(diag_raw, list):
        diag_list = [d for d in diag_raw if isinstance(d, dict)]
    elif isinstance(diag_raw, dict):
        inner = diag_raw.get("diagnostics", diag_raw)
        if isinstance(inner, list):
            diag_list = [d for d in inner if isinstance(d, dict)]

    amb_raw = _load_obj(ambiguities)
    amb_models: list[AmbiguityRecord] = list(world.ambiguities)
    if isinstance(amb_raw, list):
        amb_models = [AmbiguityRecord.model_validate(a) for a in amb_raw]

    static_obj = _load_obj(static_analysis)
    dynamic_obj = _load_obj(dynamic_validation)
    diff_obj = _load_obj(differential)
    arts_obj = _load_obj(artifacts)
    artifact_digests: dict[str, str] | None = None
    if isinstance(arts_obj, dict):
        artifact_digests = {str(k): str(v) for k, v in arts_obj.items()}

    case = build_assurance_case(
        world,
        diagnostics=diag_list,
        ambiguities=amb_models,
        static_analysis=static_obj if isinstance(static_obj, dict) else None,
        dynamic_validation=dynamic_obj if isinstance(dynamic_obj, dict) else None,
        differential=diff_obj if isinstance(diff_obj, dict) else None,
        artifacts=artifact_digests,
    )
    paths = write_assurance_report(case, output_dir)
    emit_success(
        as_json=as_json,
        message="Assurance report written (section 20).",
        extra={
            "json": str(paths["json"]),
            "html": str(paths["html"]),
            "ir_digest": case.ir_digest,
            "content_digest": case.content_digest(),
            "section_ids": [s.id for s in case.sections],
            "release_ready": case.metadata.get("release_ready"),
        },
    )
