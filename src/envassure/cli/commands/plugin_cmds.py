"""Plugin CLI group (`plugins_app`)."""

from __future__ import annotations

from pathlib import Path

import typer

from envassure.cli.output import console, emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.plugins import (
    PluginAllowlist,
    PluginKind,
    create_plugin_scaffold,
    create_plugin_template,
    discover_plugins,
    doctor_plugins,
    package_plugin,
    validate_plugin,
)

plugins_app = typer.Typer(
    name="plugins",
    help="Plugin create / test / package / doctor.",
    no_args_is_help=True,
)


@plugins_app.command("list")
def plugins_list(as_json: bool = typer.Option(False, "--json")) -> None:
    specs = discover_plugins()
    emit_success(
        as_json=as_json,
        message=f"{len(specs)} plugin(s)",
        extra={"plugins": [s.model_dump(mode="json") for s in specs]},
    )


@plugins_app.command("create")
def plugins_create(
    name: str = typer.Argument(..., help="Plugin name."),
    directory: Path = typer.Option(
        Path("plugins"),
        "--dir",
        "-d",
        help="Parent directory for the scaffold.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Optional single-file template path (legacy).",
    ),
    kind: str = typer.Option(
        "generic",
        "--kind",
        "-k",
        help="Plugin kind: generic | source_adapter | codegen_target.",
    ),
    version: str = typer.Option("0.1.0", "--version"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Scaffold a new plugin package (or single-file template with --output)."""
    normalized = kind.replace("-", "_")
    if normalized not in {"generic", "source_adapter", "codegen_target"}:
        raise typer.BadParameter("kind must be generic, source_adapter, or codegen_target")
    plugin_kind: PluginKind = normalized  # type: ignore[assignment]
    if output is not None:
        output.write_text(create_plugin_template(name, kind=plugin_kind), encoding="utf-8")
        emit_success(
            as_json=as_json,
            message=f"Wrote {output}",
            extra={"output": str(output), "kind": plugin_kind},
        )
        return
    target = directory / name.replace("-", "_")
    spec = create_plugin_scaffold(target, name=name, version=version, kind=plugin_kind)
    emit_success(
        as_json=as_json,
        message=f"Created {plugin_kind} plugin scaffold at {target}",
        extra={"plugin": spec.model_dump(mode="json"), "path": str(target)},
    )


@plugins_app.command("test")
def plugins_test(
    path: Path | None = typer.Argument(
        None,
        help="Plugin directory or plugin.json (optional).",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Test plugin spec / API compatibility (offline)."""
    if path is None:
        emit_success(
            as_json=as_json,
            message="No plugin path provided; discovered entry points only.",
            extra={"tested": [s.name for s in discover_plugins()]},
        )
        return
    report = validate_plugin(path)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    emit_success(as_json=as_json, message="Plugin test OK", report=report)


@plugins_app.command("package")
def plugins_package(
    path: Path = typer.Argument(..., help="Plugin directory."),
    output: Path = typer.Option(Path("dist/plugin.zip"), "--output", "-o"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Zip a plugin directory for distribution."""
    target = path.parent if path.is_file() else path
    out = package_plugin(target, output)
    emit_success(
        as_json=as_json,
        message=f"Packaged plugin to {out}",
        extra={"output": str(out)},
    )


@plugins_app.command("doctor")
def plugins_doctor(
    path: Path | None = typer.Argument(
        None,
        help="Optional local plugin directory to include in doctor checks.",
    ),
    allowlist: Path | None = typer.Option(
        None,
        "--allowlist",
        help="JSON object of plugin name -> version (or '*').",
    ),
    allow: list[str] | None = typer.Option(
        None,
        "--allow",
        help="Allowed plugin name (repeatable).",
    ),
    release_mode: bool = typer.Option(
        False,
        "--release",
        help="Enforce allowlist (fail closed).",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Discover plugins and optionally enforce the release allowlist."""
    alist: PluginAllowlist | set[str] | None = None
    if allowlist is not None:
        import json

        data = json.loads(allowlist.read_text(encoding="utf-8"))
        alist = PluginAllowlist.from_mapping({str(k): str(v) for k, v in data.items()})
    elif allow:
        alist = set(allow)
    report = doctor_plugins(allowlist=alist, release_mode=release_mode, path=path)
    if report.has_errors():
        emit_report(report, as_json=as_json, exit_code=ExitCode.ERROR)
    plugins = report.context.get("plugins", [])
    if not as_json:
        console.print(f"Discovered {len(plugins)} plugin(s)")
        for plugin in plugins:
            console.print(
                f"- {plugin.get('name')} {plugin.get('version')} "
                f"[{plugin.get('kind')}] "
                f"({plugin.get('entry_point') or plugin.get('module')})"
            )
    emit_success(
        as_json=as_json,
        message="Plugin doctor OK",
        report=report,
        extra={"plugins": plugins},
    )
