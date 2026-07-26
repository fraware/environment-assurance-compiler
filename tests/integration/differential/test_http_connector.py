"""HttpReferenceConnector + refund service integration tests."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from envassure.differential.http_connector import HttpReferenceConnector

REPO = Path(__file__).resolve().parents[3]
SERVER = REPO / "examples" / "reference_systems" / "refund_service" / "app" / "server.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def refund_server() -> Iterator[str]:
    port = _free_port()
    env = {
        **os.environ,
        "REFUND_SERVICE_HOST": "127.0.0.1",
        "REFUND_SERVICE_PORT": str(port),
        "ENVASURE_EVALUATOR_TOKEN": "test-token",
        "PLANT_MISMATCH": "1",
    }
    proc = subprocess.Popen(
        [sys.executable, str(SERVER)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 10
    try:
        while time.time() < deadline:
            try:
                conn = HttpReferenceConnector(
                    base,
                    allow_network=True,
                    privileged_token="test-token",
                )
                health = conn.doctor()
                if health.get("ok"):
                    yield base
                    return
            except Exception:
                time.sleep(0.1)
        out = ""
        pytest.fail(f"refund server failed to start: {out}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_http_connector_requires_network_opt_in() -> None:
    with pytest.raises(PermissionError, match="allow_network"):
        HttpReferenceConnector("http://127.0.0.1:9")


def test_http_connector_doctor_and_mismatch(refund_server: str) -> None:
    conn = HttpReferenceConnector(
        refund_server,
        allow_network=True,
        privileged_token="test-token",
    )
    assert conn.doctor()["ok"] is True
    conn.reset(seed=1)
    out = conn.execute(
        "p1",
        "get_balance",
        {"account_id": "acct-1"},
    )
    assert out.success is True
    priv = conn.probe_state()
    assert out.observation.get("balance") == 999
    assert priv["accounts"]["acct-1"]["balance"] == 1000


def test_cli_connector_doctor(refund_server: str) -> None:
    from typer.testing import CliRunner

    from envassure.cli.app import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "connector",
            "doctor",
            "--http-url",
            refund_server,
            "--allow-network",
            "--token",
            "test-token",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True


def test_differential_run_subcommand_offline(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from envassure.cli.app import app

    # Minimal world JSON for CLI wiring.
    world = {
        "environment_id": "diff.offline.v1",
        "name": "Diff Offline",
        "ir_version": "0.2.0",
        "state": [],
        "actors": [],
        "actions": [],
        "observations": [],
        "transitions": [],
        "tasks": [],
        "verifiers": [],
        "evidence_obligations": [],
        "failures": [],
        "ambiguities": [],
        "decisions": [],
    }
    ir = tmp_path / "world.json"
    # Prefer a real compiled counter world if available.
    counter = REPO / "examples" / "counter" / "world.py"
    if counter.is_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location("cworld", counter)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        compiled = mod.build_counter_world()
        ir.write_text(json.dumps(compiled.model_dump(mode="json")), encoding="utf-8")
    else:
        ir.write_text(json.dumps(world), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["differential", "run", str(ir), "--max-probes", "8", "--json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["probe_count"] >= 0


@pytest.mark.skipif(
    os.environ.get("ENVASURE_RUN_COMPOSE") != "1",
    reason="Compose tests require Docker; set ENVASURE_RUN_COMPOSE=1 in CI",
)
def test_compose_refund_service_optional() -> None:
    compose = REPO / "examples" / "reference_systems" / "refund_service" / "docker-compose.yml"
    assert compose.is_file()
    proc = subprocess.run(
        ["docker", "compose", "-f", str(compose), "config"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


# Silence unused Any in older checkers.
_ = Any
