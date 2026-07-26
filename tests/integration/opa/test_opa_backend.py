"""OPA obligation integration tests (bundle generation; opa binary optional)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from envassure.obligations.backends.opa import (
    OPA_FAMILIES,
    OpaBackendError,
    emit_rego_v1_bundle,
    opa_test,
    require_opa_binary,
)
from envassure.obligations.compiler import compile_obligations, compile_opa_bundle
from envassure.obligations.evidence import ObligationEvidence, build_evidence_report
from envassure.runtime import EventSourcedEnvironment

REPO = Path(__file__).resolve().parents[3]


def _counter_world():
    import importlib.util

    path = REPO / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("counter_world_opa", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_counter_world()


def test_six_opa_families_defined() -> None:
    assert len(OPA_FAMILIES) == 6
    assert "idempotency_safety" in OPA_FAMILIES


def test_compile_and_emit_bundle(tmp_path: Path) -> None:
    world = _counter_world()
    bundle = compile_obligations(world)
    kinds = {o.claim_kind for o in bundle.obligations}
    assert "authorization_preservation" in kinds
    assert "idempotency_safety" in kinds

    # Drop deferred/unsupported so emit succeeds under fail-closed path via filter.
    filtered = bundle.model_copy(
        update={"obligations": [o for o in bundle.obligations if o.status == "generated"]}
    )
    out = emit_rego_v1_bundle(filtered, tmp_path / "bundle")
    for name in (
        ".manifest",
        "policy.rego",
        "data.json",
        "schema.json",
        "policy_test.rego",
        "obligation-map.json",
    ):
        assert (out / name).is_file()
    policy = (out / "policy.rego").read_text(encoding="utf-8")
    assert "import rego.v1" in policy
    assert "authorization_preservation" in policy


def test_compile_opa_bundle_fails_on_unsupported(tmp_path: Path) -> None:
    from envassure.api import World

    w = World("bad.opa.v1", "Bad")
    w.state("n", type="resource_counter", initial_generator="0")
    w.actor("a", available_actions=["x"])
    w.action(
        "x",
        actor_classes=["a"],
        authorization="unsupported:custom",
        success_outcomes=["ok"],
    )
    w.transition("t", action_id="x", events=["x"])
    world = w.compile()
    with pytest.raises(OpaBackendError, match="unsupported"):
        compile_opa_bundle(world, tmp_path / "out", fail_on_unsupported=True)


def test_evidence_report_assurance_fragment() -> None:
    world = _counter_world()
    bundle = compile_obligations(world)
    evidence = [
        ObligationEvidence(
            obligation_id=bundle.obligations[0].id,
            kind="opa_test",
            status="pass",
            detail="unit",
        )
    ]
    report = build_evidence_report(bundle, evidence)
    frag = report.to_assurance_case_fragment()
    assert frag["kind"] == "obligation_evidence"
    assert frag["digest"]


@pytest.mark.skipif(shutil.which("opa") is None, reason="OPA binary not installed")
def test_opa_binary_test_suite(tmp_path: Path) -> None:
    world = _counter_world()
    bundle = compile_obligations(world)
    filtered = bundle.model_copy(
        update={"obligations": [o for o in bundle.obligations if o.status == "generated"]}
    )
    out = emit_rego_v1_bundle(filtered, tmp_path / "bundle")
    require_opa_binary()
    result = opa_test(out)
    assert result["ok"], result


def test_cli_obligations_generate(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from envassure.cli.app import app

    world = _counter_world()
    ir = tmp_path / "world.json"
    ir.write_text(json.dumps(world.model_dump(mode="json")), encoding="utf-8")
    out = tmp_path / "bundle"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["obligations", "generate", str(ir), "-o", str(out), "--allow-unsupported", "--json"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert (out / "policy.rego").is_file()


# Keep EventSourcedEnvironment import used for future runtime evidence hooks.
_ = EventSourcedEnvironment
