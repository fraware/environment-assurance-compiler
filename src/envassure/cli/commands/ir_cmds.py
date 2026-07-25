"""CLI commands for IR build/lint/diff/explain/generate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import typer

from envassure.cli.output import console, emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.diff import diff_worlds
from envassure.ir.explain import explain_element
from envassure.ir.io import load_world, save_world
from envassure.ir.models import WorldDefinition
from envassure.ir.schema import export_schemas
from envassure.ir.validate import validate_world
from envassure.workspace.layout import WorkspacePaths


def build_ir_command(
    path: Path = typer.Option(
        Path.cwd(),
        "--path",
        "-p",
        help="Workspace root or path to a Python module exporting build_*_world.",
    ),
    module: str | None = typer.Option(
        None,
        "--module",
        "-m",
        help="Python file that defines build_*_world() / compile().",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Output IR JSON path (default: <workspace>/ir/world.json).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Rebuild even when source digests are unchanged.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Compile manual SDK world into IR JSON."""
    from envassure.workspace.incremental import (
        decide_incremental_rebuild,
        record_build_state,
    )

    report = DiagnosticReport()
    root = Path(path)
    is_workspace = (root / "eac.toml").is_file()

    if is_workspace and not force:
        decision = decide_incremental_rebuild(root, force=False)
        report.extend(decision.report.diagnostics)
        out_default = root / "ir" / "world.json"
        if decision.skip and out_default.is_file():
            emit_success(
                as_json=as_json,
                message="Incremental rebuild skipped (source digests unchanged).",
                report=report,
                extra={
                    "skipped": True,
                    "reason": decision.reason,
                    "aggregate": decision.aggregate,
                    "output": str(out_default),
                },
            )
            return

    mod_path = module
    if mod_path is None:
        candidate = Path(path) / "world.py"
        if candidate.is_file():
            mod_path = str(candidate)
        else:
            report.add(
                make_diagnostic(
                    "EAC3001",
                    reason="no --module and no world.py found",
                    subject=str(path),
                )
            )
            emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)

    world = _load_builder(Path(mod_path))
    out = output
    if out is None:
        if is_workspace:
            out = root / "ir" / "world.json"
        else:
            out = Path(mod_path).resolve().parent / "ir" / "world.json"
    validation = validate_world(world)
    report.extend(validation.diagnostics)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    save_world(out, world)
    if is_workspace:
        record_build_state(
            root,
            command="build-ir",
            status="ok",
            artifact_digests={"ir": str(out)},
        )
    emit_success(
        as_json=as_json,
        message=f"Wrote IR to {out}",
        report=report,
        extra={
            "output": str(out),
            "environment_id": world.environment_id,
            "skipped": False,
        },
    )


def lint_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Lint even when IR digest matches last successful lint.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Validate IR reference integrity."""
    from envassure.workspace.incremental import (
        decide_incremental_lint,
        record_lint_state,
    )

    decision = decide_incremental_lint(ir_path, force=force)
    if decision.skip:
        emit_success(
            as_json=as_json,
            message="Incremental lint skipped (IR digest unchanged).",
            report=decision.report,
            extra={
                "skipped": True,
                "reason": decision.reason,
                "aggregate": decision.aggregate,
                "environment_id": None,
            },
        )
        return

    world = load_world(ir_path)
    report = validate_world(world)
    report.extend(decision.report.diagnostics)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    record_lint_state(ir_path, status="ok")
    emit_success(
        as_json=as_json,
        message=f"IR OK: {world.environment_id}",
        report=report,
        extra={"environment_id": world.environment_id, "skipped": False},
    )


def diff_command(
    before: Path = typer.Argument(..., help="Before IR JSON."),
    after: Path = typer.Argument(..., help="After IR JSON."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Classify semantic differences between two IR documents."""
    result = diff_worlds(load_world(before), load_world(after))
    payload = result.model_dump(mode="json")
    if as_json:
        console.print_json(json.dumps({"ok": True, "exit_code": 0, **payload}))
    else:
        console.print(f"advisory_semver: {result.advisory_semver}")
        console.print(result.advisory_rationale)
        for entry in result.entries:
            console.print(f"- [{entry.category.value}] {entry.path}: {entry.change}")
        if result.empty:
            console.print("No differences.")


def explain_command(
    ir_path: Path = typer.Argument(..., help="IR JSON path."),
    element_id: str = typer.Argument(..., help="Element id to explain."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Explain an IR element via provenance."""
    world = load_world(ir_path)
    explanation = explain_element(world, element_id)
    if explanation is None:
        report = DiagnosticReport()
        report.add(
            make_diagnostic(
                "EAC3002",
                reason=f"unknown element {element_id!r}",
                subject=element_id,
            )
        )
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "ok": True,
                    "exit_code": 0,
                    "explanation": explanation.model_dump(mode="json"),
                }
            )
        )
    else:
        console.print(f"{explanation.element_kind} {explanation.element_id}")
        console.print(explanation.summary)
        if explanation.source_ids:
            console.print(f"sources: {', '.join(explanation.source_ids)}")
        if explanation.decision_ids:
            console.print(f"decisions: {', '.join(explanation.decision_ids)}")
        if explanation.related:
            console.print(f"related: {', '.join(explanation.related)}")


def generate_command(
    path: Path = typer.Option(Path.cwd(), "--path", "-p"),
    schemas_only: bool = typer.Option(False, "--schemas", help="Export JSON schemas only."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Generate schemas and/or placeholder generated runtime stubs for a workspace."""
    paths = WorkspacePaths(root=path.resolve())
    written: list[str] = []
    if schemas_only:
        target = paths.generated_dir / "schemas" if paths.is_workspace() else Path("schemas")
        for p in export_schemas(target):
            written.append(str(p))
    elif paths.is_workspace() and paths.ir_dir.joinpath("world.json").is_file():
        world = load_world(paths.ir_dir / "world.json")
        stub = paths.generated_dir / "runtime_stub.py"
        stub.write_text(
            _runtime_stub(world.environment_id),
            encoding="utf-8",
        )
        written.append(str(stub))
        for p in export_schemas(paths.generated_dir / "schemas"):
            written.append(str(p))
    else:
        for p in export_schemas(Path("schemas")):
            written.append(str(p))
    emit_success(
        as_json=as_json,
        message="Generation complete.",
        extra={"written": written},
    )


def _load_builder(path: Path) -> WorldDefinition:
    spec = importlib.util.spec_from_file_location("eac_world_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in dir(module):
        if name.startswith("build_") and name.endswith("_world"):
            fn = getattr(module, name)
            if callable(fn):
                world = fn()
                if not isinstance(world, WorldDefinition):
                    raise RuntimeError(f"{name}() did not return WorldDefinition")
                return world
    raise RuntimeError(f"no build_*_world() found in {path}")


def _runtime_stub(environment_id: str) -> str:
    return (
        '"""Generated runtime stub — replace via eac generate (Phase 3)."""\n'
        f'ENVIRONMENT_ID = "{environment_id}"\n'
    )
