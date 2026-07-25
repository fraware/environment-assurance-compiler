"""EAC-R08 observation projections + EAC-R09 validation pipeline tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from typer.testing import CliRunner

from envassure.api import World
from envassure.cli.app import app
from envassure.ir.io import save_world
from envassure.ir.models import ActorDefinition
from envassure.ir.validate import ReleaseProfile, run_validation_pipeline, validate_world
from envassure.runtime import EventSourcedEnvironment
from envassure.runtime.observations import (
    compile_observation,
    observe_or_empty,
    project_state,
    validate_observation_projections,
)

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _load_example(name: str):
    root = REPO / "examples" / name / "world.py"
    spec = importlib.util.spec_from_file_location(f"ex_{name}_r08", root)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- R08 observations -------------------------------------------------------


def test_observe_never_leaks_full_state_without_projection() -> None:
    w = World("leak.v1", "Leak")
    w.state("secret", initial_generator="'hidden'")
    w.state("public", initial_generator="'ok'")
    w.actor("a", available_actions=["noop"])
    w.action("noop", actor_classes=["a"], success_outcomes=["ok"])
    w.transition("t", action_id="noop")
    world = w.compile()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    # Authoritative state has both keys; observe must not return them.
    assert "secret" in env.state()
    assert env.observe("a") == {}


def test_observe_unknown_projection_is_empty() -> None:
    w = World("unk.v1", "UnknownProj")
    w.state("secret", initial_generator="1")
    w.actor("a", available_actions=["noop"], observation_projection_id="missing")
    w.action("noop", actor_classes=["a"], success_outcomes=["ok"])
    w.transition("t", action_id="noop")
    world = w.compile()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    assert env.observe("a") == {}
    assert env.state() == {"secret": 1}


def test_actor_differential_observations() -> None:
    world = _load_example("auth").build_auth_world()
    env = EventSourcedEnvironment(world, strict=False)
    env.reset(
        seed=0,
        options={
            "initial_state": {
                "request_status": "pending",
                "requester_id": "u1",
                "approver_id": "oracle-secret",
            }
        },
    )

    requester = env.observe("requester")
    approver = env.observe("approver")
    assert requester == {"request_status": "pending"}
    assert "approver_id" not in requester
    assert approver == {"request_status": "pending", "requester_id": "u1"}
    assert "approver_id" not in approver
    # Differential: actors must not see identical supersets of hidden state.
    assert requester != approver
    assert "approver_id" not in requester
    assert "approver_id" not in approver


def test_unsupported_observation_semantics_rejected() -> None:
    w = World("noise.v1", "Noise")
    w.state("x", initial_generator="0")
    w.actor("a", actor_class="a", observation_projection_id="view")
    w.observation(
        "view",
        target_actor_class="a",
        visible_paths=["x"],
        noise="gaussian:0.1",
        delay="ticks:3",
        side_channel_policy="timing",
    )
    world = w.compile()
    result = compile_observation(world.observations[0], strict_unsupported=True)
    assert not result.ok
    assert any(d.code == "EAC5004" for d in result.diagnostics)

    report = validate_observation_projections(world, strict_unsupported=True)
    assert any(d.code == "EAC5004" for d in report.diagnostics)

    # Runtime fail-closed: unsupported projection not compiled ⇒ empty observe.
    w2 = World("noise2.v1", "Noise2")
    w2.state("x", initial_generator="0")
    w2.actor("a", available_actions=["noop"], observation_projection_id="view")
    w2.observation(
        "view",
        target_actor_class="a",
        visible_paths=["x"],
        staleness="max_age:5",
    )
    w2.action("noop", actor_classes=["a"], success_outcomes=["ok"])
    w2.transition("t", action_id="noop")
    env = EventSourcedEnvironment(w2.compile())
    env.reset(seed=0)
    assert env.observe("a") == {}
    assert env.state()["x"] == 0


def test_transformations_redact_and_access_control() -> None:
    w = World("xform.v1", "Xform")
    w.state("token", initial_generator="'secret-token'")
    w.state("count", initial_generator="1")
    w.actor(
        "viewer",
        actor_class="viewer",
        roles=["viewer"],
        observation_projection_id="view",
    )
    w.actor(
        "stranger",
        actor_class="stranger",
        roles=["guest"],
        observation_projection_id="view",
    )
    w.observation(
        "view",
        target_actor_class="viewer",
        visible_paths=["token", "count"],
        transformations=["redact:token"],
        access_control="role:viewer",
    )
    world = w.compile()
    compiled = compile_observation(world.observations[0]).compiled
    assert compiled is not None
    viewer = world.index_actors()["viewer"]
    stranger = world.index_actors()["stranger"]
    state = {"token": "secret-token", "count": 1}
    assert project_state(state, compiled, actor=viewer, actor_view={}) == {
        "token": None,
        "count": 1,
    }
    assert project_state(state, compiled, actor=stranger, actor_view={}) == {}


def test_observe_or_empty_helper_no_leak() -> None:
    actor = ActorDefinition(id="a", actor_class="a")
    out = observe_or_empty(
        {"secret": 1},
        actor=actor,
        projections={},
    )
    assert out == {}


def test_counter_observe_allowlist() -> None:
    world = _load_example("counter").build_counter_world()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    env.step("client", "increment")
    obs = env.observe("client")
    assert obs == {"count": 1}
    assert set(obs) == {"count"}


# --- R09 validation pipeline ------------------------------------------------


def test_authoring_profile_allows_unbound_actor() -> None:
    w = World("authz.v1", "Authoring")
    w.state("s")
    w.actor("a", available_actions=["act"])
    w.action("act", actor_classes=["a"])
    w.transition("t", action_id="act")
    report = validate_world(w.compile(), profile=ReleaseProfile.AUTHORING)
    assert not report.has_errors(), report.diagnostics


def test_executable_profile_requires_projection_binding() -> None:
    w = World("exec.v1", "Executable")
    w.state("s", initial_generator="0")
    w.actor("a", available_actions=["act"])
    w.action("act", actor_classes=["a"], intended_effects=["s = 1"], success_outcomes=["ok"])
    w.transition("t", action_id="act")
    report = validate_world(w.compile(), profile=ReleaseProfile.EXECUTABLE)
    assert report.has_errors()
    assert any(d.code == "EAC5005" for d in report.diagnostics)


def test_executable_profile_rejects_unsupported_obs() -> None:
    w = World("exec2.v1", "Executable2")
    w.state("s", initial_generator="0")
    w.actor("a", available_actions=["act"], observation_projection_id="view")
    w.observation(
        "view",
        target_actor_class="a",
        visible_paths=["s"],
        noise="gaussian",
    )
    w.action("act", actor_classes=["a"], success_outcomes=["ok"])
    w.transition("t", action_id="act")
    report = validate_world(w.compile(), profile=ReleaseProfile.EXECUTABLE)
    assert any(d.code == "EAC5004" for d in report.diagnostics)


def test_pipeline_wires_obligations_and_tasks() -> None:
    world = _load_example("counter").build_counter_world()
    # Add a broken obligation producer to force wiring.
    from envassure.ir.models import EvidenceObligation

    world.evidence_obligations.append(
        EvidenceObligation(
            id="obl.bad",
            trigger="on_action:missing",
            evidence_class="receipt",
            producer="not_an_action",
            consumer="verifier",
        )
    )
    result = run_validation_pipeline(world, profile=ReleaseProfile.EXECUTABLE)
    assert any(d.code == "EAC3002" and "obligation" in d.summary for d in result.report.diagnostics)
    assert "obligations" in result.passes_run
    assert "runtime_support" in result.passes_run
    assert "release_readiness" in result.passes_run


def test_counter_passes_executable_pipeline() -> None:
    world = _load_example("counter").build_counter_world()
    result = run_validation_pipeline(world, profile=ReleaseProfile.EXECUTABLE)
    assert not result.has_errors(), result.report.diagnostics


def test_lint_cli_profile_executable(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    ir = tmp_path / "world.json"
    save_world(ir, world)
    result = runner.invoke(app, ["lint", str(ir), "--profile", "executable", "--json"])
    assert result.exit_code == 0, result.output


def test_lint_cli_blocks_missing_projection(tmp_path: Path) -> None:
    w = World("lint.v1", "LintFail")
    w.state("s")
    w.actor("a", available_actions=["act"])
    w.action("act", actor_classes=["a"])
    w.transition("t", action_id="act")
    ir = tmp_path / "world.json"
    save_world(ir, w.compile())
    result = runner.invoke(app, ["lint", str(ir), "--profile", "executable", "--json"])
    assert result.exit_code != 0
    assert "EAC5005" in result.output


def test_research_release_blocks_open_ambiguities() -> None:
    from envassure.ir.models import AmbiguityRecord

    world = _load_example("counter").build_counter_world()
    world.ambiguities.append(
        AmbiguityRecord(
            id="amb.open",
            subject="count",
            conflict_class="test",
            default_prohibition="do not release",
            operational_consequence="blocks release",
            required_expert_role="owner",
            status="open",
        )
    )
    report = validate_world(world, profile=ReleaseProfile.RESEARCH_RELEASE)
    assert any(d.code in {"EAC2001", "EAC3007"} for d in report.diagnostics)
    assert report.has_errors()
