"""CLI: ``eac export|serve openenv`` and ``eac openenv test``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
import yaml

from envassure.cli.output import emit_report, emit_success
from envassure.codegen.openenv_target import export_openenv_scaffold
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.io import load_world
from envassure.runtime import EventSourcedEnvironment
from envassure.runtime.adapters.common import AdapterSemanticsError
from envassure.runtime.adapters.openenv_service import (
    PINNED_OPENENV_VERSION,
    EnvAssureOpenEnvAction,
    OpenEnvAssureService,
    check_openenv_pin,
)

export_app = typer.Typer(
    name="export",
    help="Export Environment IR to external runtime targets.",
    no_args_is_help=True,
)

serve_app = typer.Typer(
    name="serve",
    help="Serve exported runtime targets locally.",
    no_args_is_help=True,
)

openenv_app = typer.Typer(
    name="openenv",
    help="OpenEnv adapter export / serve / test (experimental pin openenv==0.4.1).",
    no_args_is_help=True,
)


@export_app.command("openenv")
@openenv_app.command("export")
def export_openenv(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    output: Path = typer.Option(Path("openenv_export"), "--output", "-o"),
    actor_id: str = typer.Option(..., "--actor-id", help="Primary actor for the service."),
    name: str | None = typer.Option(None, "--name"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Export an OpenEnv scaffold (openenv.yaml, server, Dockerfile, manifests)."""
    world = load_world(ir_path)
    try:
        path = export_openenv_scaffold(world, output, actor_id=actor_id, name=name)
    except (ValueError, AdapterSemanticsError) as exc:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    emit_success(
        as_json=as_json,
        message=f"OpenEnv scaffold written to {path}",
        extra={
            "path": str(path),
            "openenv_pin": PINNED_OPENENV_VERSION,
            "actor_id": actor_id,
            "members": [
                "openenv.yaml",
                "server/environment.py",
                "Dockerfile",
                "README.md",
                "world.json",
                "release-manifest.json",
            ],
        },
    )


@serve_app.command("openenv")
@openenv_app.command("serve")
def serve_openenv(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Scaffold directory."),
    seed: int = typer.Option(0, "--seed"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Smoke-serve: load scaffold and perform reset (HTTP server deferred / unstable)."""
    try:
        service, meta = _load_scaffold_service(directory)
        obs = service.reset(seed=seed, options={"episode_id": "serve-smoke"})
    except Exception as exc:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    emit_success(
        as_json=as_json,
        message="OpenEnv serve smoke reset OK (full HTTP serve not claimed)",
        extra={
            "meta": meta,
            "observation": obs.model_dump(mode="json"),
            "limitation": (
                "Upstream OpenEnv HTTP/server APIs remain experimental; "
                "this command validates the EnvAssure adapter path only."
            ),
        },
    )


@openenv_app.command("test")
def test_openenv(
    directory: Path = typer.Option(Path("."), "--dir", "-d", help="Scaffold directory."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Deterministic same-seed reset + one step smoke test."""
    try:
        pin = check_openenv_pin(require_exact=False)
        service, meta = _load_scaffold_service(directory)
        a = service.reset(seed=7, options={"episode_id": "t1"}).model_dump(mode="json")
        b = service.reset(seed=7, options={"episode_id": "t2"}).model_dump(mode="json")
        # Compare observation payloads (episode ids differ by design).
        same = a["observation"] == b["observation"] and a["encoded"] == b["encoded"]
        legal = a.get("legal_actions") or []
        step_result = None
        if legal:
            step_result = service.step(
                EnvAssureOpenEnvAction(
                    action_id=str(legal[0]),
                    actor_id=meta["actor_id"],
                    payload={},
                )
            ).model_dump(mode="json")
        forked = service.fork_episode()
        fork_obs = forked.reset(seed=7).model_dump(mode="json")
    except Exception as exc:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    if not same:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": "same-seed reset not deterministic", "a": a, "b": b},
        )
        return
    emit_success(
        as_json=as_json,
        message="OpenEnv adapter tests passed",
        extra={
            "pin": pin,
            "meta": meta,
            "deterministic_reset": True,
            "step": step_result,
            "fork_observation": fork_obs["observation"],
        },
    )


def _load_scaffold_service(directory: Path) -> tuple[OpenEnvAssureService, dict[str, Any]]:
    root = directory.resolve()
    cfg_path = root / "openenv.yaml"
    world_path = root / "world.json"
    if not cfg_path.is_file() or not world_path.is_file():
        raise FileNotFoundError("openenv.yaml and world.json are required in --dir")
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("openenv.yaml must be a mapping")
    actor_id = str(raw.get("actor_id") or "")
    if not actor_id:
        raise ValueError("openenv.yaml missing actor_id")
    world = load_world(world_path)
    env = EventSourcedEnvironment(world, default_actor_id=actor_id)
    service = OpenEnvAssureService(env, actor_id=actor_id)
    meta = {
        "actor_id": actor_id,
        "environment_id": world.environment_id,
        "openenv_pin": raw.get("openenv_pin", PINNED_OPENENV_VERSION),
        "name": raw.get("name"),
    }
    return service, meta
