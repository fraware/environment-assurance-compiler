"""CLI smoke tests for init, doctor, stubs, and --json."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from envassure.cli.app import app

runner = CliRunner()


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "doctor" in result.stdout
    assert "build-ir" in result.stdout
    assert "package" in result.stdout
    assert "migrate" in result.stdout


def test_cli_user_facing_help_is_ascii() -> None:
    """Legacy Windows consoles choke on arrows/em-dashes in Typer help text."""
    from typer.main import get_command

    root = get_command(app)
    texts: list[str] = [app.info.help or ""]
    for command in root.commands.values():
        texts.append(command.help or "")
        texts.append(command.short_help or "")
        for param in command.params:
            texts.append(getattr(param, "help", None) or "")
        for sub in getattr(command, "commands", {}) or {}:
            child = command.commands[sub]
            texts.append(child.help or "")
            for param in child.params:
                texts.append(getattr(param, "help", None) or "")
    joined = "\n".join(texts)
    assert all(ord(ch) < 128 for ch in joined), "non-ASCII help text found"


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "envassure" in result.stdout


def test_init_and_doctor(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    result = runner.invoke(app, ["init", str(ws), "--name", "ws"])
    assert result.exit_code == 0, result.output
    assert (ws / "eac.toml").is_file()

    result = runner.invoke(app, ["doctor", "--path", str(ws)])
    assert result.exit_code == 0, result.output


def test_init_json(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    result = runner.invoke(app, ["init", str(ws), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert "eac.toml" in payload["created"]


def test_doctor_without_workspace_ok() -> None:
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_plugins_help() -> None:
    result = runner.invoke(app, ["plugins", "--help"])
    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "create" in result.stdout


def test_refine_and_benchmark_help() -> None:
    refine = runner.invoke(app, ["refine", "--help"])
    assert refine.exit_code == 0
    bench = runner.invoke(app, ["benchmark", "--help"])
    assert bench.exit_code == 0
    assert (
        "fixture" in bench.stdout.lower()
        or "oracle" in bench.stdout.lower()
        or "Ablation" in bench.stdout
        or "ablation" in bench.stdout
    )
