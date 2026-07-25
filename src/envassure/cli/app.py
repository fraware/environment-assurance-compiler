"""Typer application and command registration."""

from __future__ import annotations

import typer

from envassure import __version__
from envassure.cli.commands import (
    analysis_cmds,
    benchmark_cmd,
    diffval_cmds,
    doctor,
    import_cmds,
    init_cmd,
    inspect_cmd,
    ir_cmds,
    migrate_cmd,
    pack_cmds,
    plugin_cmds,
    refine_cmd,
    runtime_cmds,
)

app = typer.Typer(
    name="eac",
    help="Environment Assurance Compiler - local-first evidence to IR, runtime, and packs.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"envassure {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: bool | None = typer.Option(
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Environment Assurance Compiler CLI."""


# Phase 0
app.command("init")(init_cmd.init_command)
app.command("doctor")(doctor.doctor_command)
app.command("inspect")(inspect_cmd.inspect_command)

# Phase 1
app.command("build-ir")(ir_cmds.build_ir_command)
app.command("lint")(ir_cmds.lint_command)
app.command("diff")(ir_cmds.diff_command)
app.command("explain")(ir_cmds.explain_command)
app.command("generate")(ir_cmds.generate_command)
app.command("migrate")(migrate_cmd.migrate_command)

# Phase 2
app.command("import")(import_cmds.import_command)
app.command("facts")(import_cmds.facts_command)
app.command("ambiguities")(import_cmds.ambiguities_command)
app.command("decide")(import_cmds.decide_command)

# Phase 3
app.command("run")(runtime_cmds.run_command)
app.command("snapshot")(runtime_cmds.snapshot_command)
app.command("replay")(runtime_cmds.replay_command)
app.command("test")(runtime_cmds.test_command)

# Phase 4
app.command("analyze")(analysis_cmds.analyze_command)
app.command("coverage")(analysis_cmds.coverage_command)

# Phase 5
app.command("differential")(diffval_cmds.differential_command)

# Phase 5/6 refinement + reports + plugins + benchmark
app.command("refine")(refine_cmd.refine_command)
app.command("package")(pack_cmds.package_command)
app.command("verify-pack")(pack_cmds.verify_pack_command)
app.command("report")(pack_cmds.report_command)
app.command("benchmark")(benchmark_cmd.benchmark_command)
app.add_typer(plugin_cmds.plugins_app, name="plugins")

# All required CLI commands are registered with real implementations (fail-closed
# on unsupported inputs; never silent success for unimplemented work).
STUB_COMMANDS: tuple[str, ...] = ()
