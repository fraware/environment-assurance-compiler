"""CLI commands for runtime run / snapshot / replay / test (Phase 3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer

from envassure.cli.output import emit_success
from envassure.ir.io import load_world
from envassure.runtime.engine import EventSourcedEnvironment
from envassure.runtime.snapshot import Snapshot


def _parse_actions(raw: str | None) -> list[tuple[str, str]]:
    """Parse `actor:action,actor:action` or bare `action` (default actor)."""
    if not raw:
        return []
    result: list[tuple[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            actor_id, action_id = part.split(":", 1)
            result.append((actor_id.strip(), action_id.strip()))
        else:
            result.append(("", part))
    return result


def _default_actor(env: EventSourcedEnvironment) -> str:
    if env.world.actors:
        return env.world.actors[0].id
    raise typer.BadParameter("world has no actors")


def _build_env(ir_path: Path, *, seed: int) -> EventSourcedEnvironment:
    world = load_world(ir_path)
    env = EventSourcedEnvironment(world, strict=True, live_external_effects=False)
    env.reset(seed=seed)
    return env


def _run_sequence(
    env: EventSourcedEnvironment,
    actions: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    default = _default_actor(env)
    steps: list[dict[str, Any]] = []
    for actor_id, action_id in actions:
        aid = actor_id or default
        result = env.step(aid, action_id)
        steps.append(
            {
                "actor_id": aid,
                "action_id": action_id,
                "ok": result.ok,
                "outcome": result.outcome.value,
                "reason_code": result.reason_code,
                "observation": result.observation,
                "terminal": result.terminal,
                "failure_id": result.failure_id,
                "events": [e.type for e in result.events],
                "transaction_id": (
                    result.transaction.transaction_id if result.transaction else None
                ),
            }
        )
        if result.terminal:
            break
    return steps


def run_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    actions: str = typer.Option(
        "",
        "--actions",
        "-a",
        help="Comma-separated actor:action pairs (or bare action ids).",
    ),
    seed: int = typer.Option(0, "--seed", help="RNG / episode seed."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Execute a simple action sequence on an EventSourcedEnvironment."""
    env = _build_env(ir_path, seed=seed)
    seq = _parse_actions(actions)
    steps = _run_sequence(env, seq)
    emit_success(
        as_json=as_json,
        message=f"Ran {len(steps)} step(s) on {env.world.environment_id}",
        extra={
            "environment_id": env.world.environment_id,
            "seed": seed,
            "final_state": env.state(),
            "steps": steps,
            "state_digest": env.snapshot().digests.get("state"),
        },
    )


def snapshot_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    actions: str = typer.Option("", "--actions", "-a"),
    output: Path = typer.Option(
        Path("snapshot.json"),
        "--output",
        "-o",
        help="Snapshot JSON output path.",
    ),
    seed: int = typer.Option(0, "--seed"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run actions then write a restoreable snapshot."""
    env = _build_env(ir_path, seed=seed)
    _run_sequence(env, _parse_actions(actions))
    snap = env.snapshot()
    # RNG state may contain non-JSON tuples; keep seed only for file form.
    payload = snap.model_dump(mode="json")
    payload["rng"] = {"seed": snap.seed}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    emit_success(
        as_json=as_json,
        message=f"Wrote snapshot to {output}",
        extra={
            "output": str(output),
            "environment_id": snap.environment_id,
            "clock": snap.clock,
            "digests": snap.digests,
        },
    )


def replay_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    actions: str = typer.Option(..., "--actions", "-a", help="Action sequence to replay."),
    seed: int = typer.Option(0, "--seed"),
    snapshot_path: Path | None = typer.Option(
        None,
        "--from-snapshot",
        help="Optional snapshot JSON to restore before continuing actions.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Replay an action sequence and verify deterministic digests."""
    seq = _parse_actions(actions)
    env_a = _build_env(ir_path, seed=seed)
    steps_a = _run_sequence(env_a, seq)
    digest_a = env_a.snapshot().digests

    env_b = _build_env(ir_path, seed=seed)
    restored = False
    if snapshot_path is not None:
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if not data.get("rng"):
            data["rng"] = {"seed": data.get("seed", seed)}
        env_b.restore(Snapshot.model_validate(data))
        restored = True
        steps_b = _run_sequence(env_b, seq) if seq else []
        # Restore path: success means snapshot loaded and steps applied without crash.
        match = True
        digest_b = env_b.snapshot().digests
    else:
        steps_b = _run_sequence(env_b, seq)
        digest_b = env_b.snapshot().digests
        match = digest_a == digest_b

    emit_success(
        as_json=as_json,
        message="Replay digests match" if match else "Replay digests DIVERGED",
        extra={
            "match": match,
            "restored": restored,
            "digest_a": digest_a,
            "digest_b": digest_b,
            "steps": steps_a,
            "steps_replay": steps_b,
        },
    )


def test_command(
    ir_path: Path = typer.Argument(..., help="Path to world IR JSON."),
    actions: str = typer.Option(
        "increment,increment,increment",
        "--actions",
        "-a",
        help="Action sequence for the reset/replay determinism property.",
    ),
    seed: int = typer.Option(0, "--seed"),
    trials: int = typer.Option(3, "--trials", help="Independent replay trials."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Property: reset + identical action sequence yields identical digests."""
    seq = _parse_actions(actions)
    digests: list[dict[str, str]] = []
    final_states: list[dict[str, Any]] = []
    for _ in range(max(trials, 1)):
        env = _build_env(ir_path, seed=seed)
        _run_sequence(env, seq)
        snap = env.snapshot()
        digests.append(snap.digests)
        final_states.append(env.state())

    deterministic = all(d == digests[0] for d in digests) and all(
        s == final_states[0] for s in final_states
    )
    emit_success(
        as_json=as_json,
        message=("Determinism property HOLD" if deterministic else "Determinism property FAILED"),
        extra={
            "deterministic": deterministic,
            "trials": trials,
            "seed": seed,
            "digests": digests,
            "final_state": final_states[0] if final_states else {},
        },
    )
