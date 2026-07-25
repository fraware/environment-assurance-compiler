"""Phase 1 IR / SDK / validation tests."""

from __future__ import annotations

# Import examples via file path helpers
import importlib.util
import json
from pathlib import Path

from typer.testing import CliRunner

from envassure import World, __version__
from envassure.cli.app import app
from envassure.ir.diff import DiffCategory, diff_worlds
from envassure.ir.explain import explain_element
from envassure.ir.io import save_world
from envassure.ir.schema import export_schemas, world_json_schema
from envassure.ir.validate import validate_world


def _load_example(name: str):
    root = Path(__file__).resolve().parents[1] / "examples" / name / "world.py"
    spec = importlib.util.spec_from_file_location(f"ex_{name}", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_counter_world_validates() -> None:
    world = _load_example("counter").build_counter_world()
    report = validate_world(world)
    assert not report.has_errors(), report.diagnostics
    assert world.environment_id == "counter.v1"


def test_auth_world_validates() -> None:
    world = _load_example("auth").build_auth_world()
    report = validate_world(world)
    assert not report.has_errors()
    assert any(a.id == "approve" for a in world.actions)


def test_sdk_builds_same_shape() -> None:
    w = World("x", "X")
    w.state("s")
    w.actor("a", available_actions=["act"])
    w.action("act", actor_classes=["a"])
    w.transition("t", action_id="act")
    compiled = w.compile()
    assert compiled.state[0].id == "s"
    assert not validate_world(compiled).has_errors()


def test_broken_reference_diagnosed() -> None:
    w = World("x", "X")
    w.action("act", actor_classes=["missing"])
    w.transition("t", action_id="act")
    report = validate_world(w.compile())
    assert report.has_errors()
    assert any(d.code == "EAC3002" for d in report.diagnostics)


def test_retry_undefined_eac4027() -> None:
    w = World("x", "X")
    w.actor("a", available_actions=["act"])
    w.action("act", actor_classes=["a"], timeout_behavior="fail", retry_behavior=None)
    w.transition("t", action_id="act")
    report = validate_world(w.compile())
    assert any(d.code == "EAC4027" for d in report.diagnostics)


def test_diff_and_semver() -> None:
    a = _load_example("counter").build_counter_world()
    b = a.model_copy(deep=True)
    b.actions[0].authorization = "role:admin"
    result = diff_worlds(a, b)
    assert any(e.category is DiffCategory.PERMISSION for e in result.entries)
    assert result.advisory_semver == "major"


def test_explain() -> None:
    world = _load_example("counter").build_counter_world()
    expl = explain_element(world, "increment")
    assert expl is not None
    assert expl.element_kind == "action"
    assert "manual" in expl.source_ids


def test_schema_export(tmp_path: Path) -> None:
    schema = world_json_schema()
    assert schema["$schema"].endswith("2020-12/schema")
    paths = export_schemas(tmp_path)
    assert paths
    data = json.loads(paths[0].read_text(encoding="utf-8"))
    assert data["title"] == "WorldDefinition"


def test_cli_build_lint_diff_explain(tmp_path: Path) -> None:
    runner = CliRunner()
    world_py = Path(__file__).resolve().parents[1] / "examples" / "counter" / "world.py"
    out = tmp_path / "world.json"
    r = runner.invoke(app, ["build-ir", "--module", str(world_py), "-o", str(out)])
    assert r.exit_code == 0, r.output
    assert out.is_file()
    r = runner.invoke(app, ["lint", str(out)])
    assert r.exit_code == 0, r.output
    out2 = tmp_path / "world2.json"
    world = _load_example("counter").build_counter_world()
    world.version = "0.2.0"
    save_world(out2, world)
    r = runner.invoke(app, ["diff", str(out), str(out2), "--json"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["explain", str(out), "count"])
    assert r.exit_code == 0, r.output
    assert __version__
