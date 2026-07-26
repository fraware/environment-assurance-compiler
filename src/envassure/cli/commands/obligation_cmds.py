"""CLI group: ``eac obligations generate|test|evaluate|report``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.io import load_world
from envassure.obligations.backends.opa import (
    OpaBackendError,
    opa_eval,
    opa_fmt_check,
    opa_test,
    require_opa_binary,
)
from envassure.obligations.compiler import compile_obligations, compile_opa_bundle
from envassure.obligations.evidence import (
    ObligationEvidence,
    build_evidence_report,
)
from envassure.obligations.generators import validate_proof_obligations

obligations_app = typer.Typer(
    name="obligations",
    help="Compile and evaluate proof obligations (OPA / Rego v1 backend).",
    no_args_is_help=True,
)


@obligations_app.command("generate")
def obligations_generate(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    output: Path = typer.Option(
        Path("obligations-bundle"),
        "--output",
        "-o",
        help="Directory for Rego v1 OPA bundle.",
    ),
    allow_unsupported: bool = typer.Option(
        False,
        "--allow-unsupported",
        help="Skip unsupported obligations instead of failing closed.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Generate a Rego v1 OPA bundle from Environment IR."""
    world = load_world(ir_path)
    try:
        bundle, path = compile_opa_bundle(
            world,
            output,
            fail_on_unsupported=not allow_unsupported,
        )
    except OpaBackendError as exc:
        report = DiagnosticReport(context={"environment_id": world.environment_id})
        emit_report(
            report,
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    emit_success(
        as_json=as_json,
        message=f"OPA bundle written to {path}",
        extra={
            "environment_id": world.environment_id,
            "obligation_count": len(bundle.obligations),
            "bundle_dir": str(path),
            "bundle_digest": bundle.content_digest(),
            "members": [
                ".manifest",
                "policy.rego",
                "data.json",
                "schema.json",
                "policy_test.rego",
                "obligation-map.json",
            ],
        },
    )


@obligations_app.command("test")
def obligations_test(
    bundle_dir: Path = typer.Argument(..., help="OPA bundle directory."),
    skip_fmt: bool = typer.Option(False, "--skip-fmt"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run ``opa fmt --check`` and ``opa test --fail-on-empty`` on a bundle."""
    try:
        opa = require_opa_binary()
    except OpaBackendError as exc:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    results: dict[str, Any] = {"opa": opa}
    if not skip_fmt:
        results["fmt"] = opa_fmt_check(bundle_dir, opa_path=opa)
    results["test"] = opa_test(bundle_dir, opa_path=opa)
    ok = results["test"].get("ok") and (skip_fmt or results.get("fmt", {}).get("ok"))
    if not ok:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra=results,
        )
        return
    emit_success(as_json=as_json, message="OPA obligation tests passed", extra=results)


@obligations_app.command("evaluate")
def obligations_evaluate(
    bundle_dir: Path = typer.Argument(..., help="OPA bundle directory."),
    input_path: Path = typer.Option(
        ...,
        "--input",
        "-i",
        help="JSON input document for opa eval.",
    ),
    query: str = typer.Option(
        "data.envassure.obligations.allow",
        "--query",
        "-q",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Evaluate an OPA query against a generated bundle."""
    try:
        opa = require_opa_binary()
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise OpaBackendError("input must be a JSON object")
        result = opa_eval(bundle_dir, payload, query=query, opa_path=opa)
    except (OpaBackendError, json.JSONDecodeError, OSError) as exc:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    if not result.get("ok"):
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra=result,
        )
        return
    emit_success(as_json=as_json, message="OPA evaluate complete", extra=result)


@obligations_app.command("report")
def obligations_report(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    evidence_path: Path | None = typer.Option(
        None,
        "--evidence",
        help="Optional JSON list of ObligationEvidence records.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Write assurance-case fragment JSON here.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Compile obligations and emit an assurance-case evidence fragment."""
    world = load_world(ir_path)
    bundle = compile_obligations(world)
    report = validate_proof_obligations(bundle, world=world)
    evidence_items: list[ObligationEvidence] = []
    if evidence_path is not None:
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            emit_report(
                DiagnosticReport(),
                as_json=as_json,
                exit_code=ExitCode.ERROR,
                extra={"error": "evidence file must be a JSON list"},
            )
            return
        evidence_items = [ObligationEvidence.model_validate(item) for item in raw]
    evidence_report = build_evidence_report(bundle, evidence_items)
    fragment = evidence_report.to_assurance_case_fragment()
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(fragment, indent=2) + "\n", encoding="utf-8")
    extra = {
        "environment_id": world.environment_id,
        "obligation_count": len(bundle.obligations),
        "bundle_digest": bundle.content_digest(),
        "assurance_case_fragment": fragment,
        "validation": report.model_dump(mode="json"),
    }
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR, extra=extra)
        return
    emit_success(
        as_json=as_json,
        message=f"Obligation report for {world.environment_id}",
        report=report,
        extra=extra,
    )
