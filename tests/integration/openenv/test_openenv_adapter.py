"""OpenEnv adapter integration tests (best-effort; openenv pin optional)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from envassure.runtime import EventSourcedEnvironment
from envassure.runtime.adapters.openenv_service import (
    PINNED_OPENENV_VERSION,
    EnvAssureOpenEnvAction,
    OpenEnvAssureService,
)

REPO = Path(__file__).resolve().parents[3]


def _counter_world():
    import importlib.util

    path = REPO / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("counter_oe", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_counter_world()


def test_openenv_pin_constant() -> None:
    assert PINNED_OPENENV_VERSION == "0.4.1"


def test_openenv_service_reset_step_fork() -> None:
    pytest.importorskip("gymnasium")
    world = _counter_world()
    # openenv import is required by service ctor
    pytest.importorskip("openenv")
    inner = EventSourcedEnvironment(world, default_actor_id="client")
    svc = OpenEnvAssureService(inner, actor_id="client")
    a = svc.reset(seed=3, options={"episode_id": "a"})
    b = svc.reset(seed=3, options={"episode_id": "b"})
    assert a.observation == b.observation
    stepped = svc.step(
        EnvAssureOpenEnvAction(action_id="increment", actor_id="client", payload={})
    )
    assert stepped.observation.get("count") == 1
    forked = svc.fork_episode()
    assert forked.state().authoritative_state == svc.state().authoritative_state


def test_export_scaffold_and_cli(tmp_path: Path) -> None:
    pytest.importorskip("gymnasium")
    from typer.testing import CliRunner

    from envassure.cli.app import app
    from envassure.codegen.openenv_target import export_openenv_scaffold

    world = _counter_world()
    out = export_openenv_scaffold(world, tmp_path / "oe", actor_id="client")
    for name in (
        "openenv.yaml",
        "server/environment.py",
        "Dockerfile",
        "README.md",
        "world.json",
        "release-manifest.json",
    ):
        assert (out / name).is_file()

    ir = tmp_path / "world.json"
    ir.write_text(json.dumps(world.model_dump(mode="json")), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "export",
            "openenv",
            str(ir),
            "-o",
            str(tmp_path / "cli_oe"),
            "--actor-id",
            "client",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
