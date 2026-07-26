"""Forward-plan workstreams: CEGR, reports §20, plugins, benchmark, incremental."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from envassure.benchmark import (
    AblationConfig,
    load_fixture_oracle,
    run_ablation_sweep,
    run_fixture_benchmark,
    score_episodes,
)
from envassure.cli.app import app
from envassure.plugins import create_plugin_scaffold, package_plugin, validate_plugin
from envassure.reconciliation.cegr import (
    apply_cegr,
    counterexample_from_mapping,
    list_refinement_generations,
)
from envassure.reports import (
    ASSURANCE_CASE_SECTIONS,
    assurance_pack_members,
    build_assurance_case,
    load_assurance_case,
    write_assurance_report,
)
from envassure.workspace.incremental import (
    decide_incremental_rebuild,
    digest_workspace_sources,
    record_build_state,
)
from envassure.workspace.init import init_workspace

runner = CliRunner()
REPO = Path(__file__).resolve().parents[1]


def _load_example(name: str):
    root = REPO / "examples" / name / "world.py"
    spec = importlib.util.spec_from_file_location(f"ex_{name}", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cegr_intake_produces_ambiguity_facts_and_patches(tmp_path: Path) -> None:
    intake = counterexample_from_mapping(
        {
            "probe_id": "p-auth-1",
            "action_id": "approve",
            "failing_dimensions": ["authorization", "failure"],
            "minimized_sequence": ["approve"],
            "original_sequence": ["observe", "approve", "observe"],
            "reference_outcome": {
                "success": False,
                "authorized": False,
                "failure": "forbidden",
            },
            "candidate_outcome": {"success": True, "authorized": True, "failure": None},
            "preserved_failure": True,
        }
    )
    result = apply_cegr(intake, workspace_root=tmp_path, persist=True)
    assert result.ambiguities
    assert any(a.conflict_class == "differential_counterexample" for a in result.ambiguities)
    assert result.corrected_facts
    assert result.transition_patches
    assert result.generation_dir is not None
    gen_dir = Path(result.generation_dir)
    assert (gen_dir / "generation.json").is_file()
    assert (gen_dir / "intake.json").is_file()
    assert (gen_dir / "ambiguities.json").is_file()
    gens = list_refinement_generations(tmp_path)
    assert len(gens) == 1
    assert gens[0].generation == 1

    # Second generation increments and preserves lineage index.
    result2 = apply_cegr(intake, workspace_root=tmp_path, persist=True)
    assert result2.generation.generation == 2
    assert len(list_refinement_generations(tmp_path)) == 2
    index = json.loads((tmp_path / "validation" / "refinements" / "index.json").read_text())
    assert [e["generation"] for e in index] == [1, 2]


def test_cegr_cli_refine(tmp_path: Path) -> None:
    intake_path = tmp_path / "ce.json"
    intake_path.write_text(
        json.dumps(
            {
                "probe_id": "cli-ce",
                "action_id": "increment",
                "failing_dimensions": ["state"],
                "minimized_sequence": ["increment"],
                "reference_outcome": {"state": {"value": 2}},
                "candidate_outcome": {"state": {"value": 3}},
            }
        ),
        encoding="utf-8",
    )
    ws = tmp_path / "ws"
    init_workspace(ws, name="cegr")
    result = runner.invoke(
        app,
        ["refine", str(intake_path), "--workspace", str(ws), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["generation"] == 1
    assert (ws / "validation" / "refinements" / "gen-0001" / "generation.json").is_file()


def test_assurance_case_has_section_20_html(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    case = build_assurance_case(
        world,
        diagnostics=[{"severity": "warning", "code": "EAC6001", "summary": "note"}],
        artifacts={"ir": "deadbeef"},
        differential={"status": "partial", "metrics": {"matched": 9, "total": 10}},
        generated_at="2026-01-01T00:00:00+00:00",
    )
    assert len(case.sections) == len(ASSURANCE_CASE_SECTIONS)
    assert [s.id for s in case.sections] == [sid for sid, _ in ASSURANCE_CASE_SECTIONS]
    written = write_assurance_report(case, tmp_path)
    html = written["html"].read_text(encoding="utf-8")
    assert "§20 sections" in html
    assert "20.12" in html
    assert "Fidelity profile" in html
    loaded = load_assurance_case(written["json"])
    assert loaded.content_digest() == case.content_digest()
    members = assurance_pack_members(case)
    assert "reports/assurance-case.json" in members
    assert "reports/assurance-case.html" in members


def test_report_cli_section_ids(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    ir = tmp_path / "world.json"
    ir.write_text(json.dumps(world.model_dump(mode="json")), encoding="utf-8")
    out = tmp_path / "reports"
    result = runner.invoke(app, ["report", str(ir), "-o", str(out), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["section_ids"][0] == "20.1"
    assert payload["section_ids"][-1] == "20.12"
    assert (out / "assurance-case.html").is_file()


def test_plugin_sdk_templates_offline_e2e(tmp_path: Path) -> None:
    for kind in ("source_adapter", "codegen_target"):
        target = tmp_path / kind
        spec = create_plugin_scaffold(target, name=f"demo-{kind.replace('_', '-')}", kind=kind)
        assert spec.kind == kind
        report = validate_plugin(target)
        assert not report.has_errors(), report.diagnostics
        zipped = package_plugin(target, tmp_path / f"{kind}.zip")
        assert zipped.is_file()
        with zipfile.ZipFile(zipped) as zf:
            names = zf.namelist()
            assert "plugin.json" in names
            assert "pyproject.toml" in names

    # CLI create → test → package → doctor
    plugin_root = tmp_path / "cli_plugins"
    create = runner.invoke(
        app,
        [
            "plugins",
            "create",
            "acme-openapi",
            "--dir",
            str(plugin_root),
            "--kind",
            "source_adapter",
            "--json",
        ],
    )
    assert create.exit_code == 0, create.output
    scaffold = plugin_root / "acme_openapi"
    tested = runner.invoke(app, ["plugins", "test", str(scaffold), "--json"])
    assert tested.exit_code == 0, tested.output
    packaged = runner.invoke(
        app,
        [
            "plugins",
            "package",
            str(scaffold),
            "-o",
            str(tmp_path / "acme.zip"),
            "--json",
        ],
    )
    assert packaged.exit_code == 0, packaged.output
    doctor = runner.invoke(app, ["plugins", "doctor", str(scaffold), "--json"])
    assert doctor.exit_code == 0, doctor.output


def test_fixture_benchmark_metrics_and_ablation() -> None:
    path = REPO / "benchmarks" / "fixtures" / "counter_oracle.json"
    oracle = load_fixture_oracle(path)
    scores = score_episodes(oracle.episodes)
    assert scores.auth_agreement is not None
    assert scores.failure_agreement is not None
    assert scores.leakage is not None and scores.leakage > 0
    assert scores.solvability is not None
    report = run_fixture_benchmark(path, case_id="counter")
    assert report.episode_count == 3
    assert report.oracle_digest
    sweep = run_ablation_sweep(
        path, [AblationConfig(name="full"), AblationConfig(name="cap", max_probes=1)]
    )
    assert sweep[1].episode_count == 1


def test_benchmark_cli(tmp_path: Path) -> None:
    fixture = REPO / "benchmarks" / "fixtures" / "auth_oracle.json"
    out = tmp_path / "bench.json"
    result = runner.invoke(
        app,
        ["benchmark", str(fixture), "-o", str(out), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["report"]["episode_count"] == 3
    assert out.is_file()


def test_incremental_rebuild_digest_stable_noop(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    init = init_workspace(ws, name="inc")
    assert not init.report.has_errors()
    (ws / "sources" / "a.txt").write_text("alpha\n", encoding="utf-8")

    first = digest_workspace_sources(ws)
    record_build_state(ws, command="build-ir", status="ok", source_digests=first.digests)
    decision = decide_incremental_rebuild(ws)
    assert decision.skip is True
    assert any(d.code == "EAC8007" for d in decision.report.diagnostics)

    # Digest-stable: recompute matches.
    again = digest_workspace_sources(ws)
    assert again.digests == first.digests
    assert again.aggregate == first.aggregate

    # Mutate source → must rebuild.
    (ws / "sources" / "a.txt").write_text("beta\n", encoding="utf-8")
    drifted = decide_incremental_rebuild(ws)
    assert drifted.skip is False
    assert "drift" in drifted.reason

    forced = decide_incremental_rebuild(ws, force=True)
    assert forced.skip is False
    assert forced.reason == "forced rebuild"


def test_build_ir_incremental_skip(tmp_path: Path) -> None:
    # Minimal workspace with world.py that builds counter-like IR via example copy.
    ws = tmp_path / "ws"
    init_workspace(ws, name="inc-cli")
    world_py = REPO / "examples" / "counter" / "world.py"
    (ws / "world.py").write_text(world_py.read_text(encoding="utf-8"), encoding="utf-8")
    (ws / "sources" / "note.txt").write_text("v1\n", encoding="utf-8")

    first = runner.invoke(app, ["build-ir", "--path", str(ws), "--json"])
    assert first.exit_code == 0, first.output
    assert (ws / "ir" / "world.json").is_file()
    payload1 = json.loads(first.stdout)
    assert payload1.get("skipped") is False

    second = runner.invoke(app, ["build-ir", "--path", str(ws), "--json"])
    assert second.exit_code == 0, second.output
    payload2 = json.loads(second.stdout)
    assert payload2["skipped"] is True

    (ws / "sources" / "note.txt").write_text("v2\n", encoding="utf-8")
    third = runner.invoke(app, ["build-ir", "--path", str(ws), "--json"])
    assert third.exit_code == 0, third.output
    payload3 = json.loads(third.stdout)
    assert payload3["skipped"] is False


def test_lint_incremental_skip(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    init_workspace(ws, name="lint-inc")
    world = _load_example("counter").build_counter_world()
    ir = ws / "ir" / "world.json"
    ir.parent.mkdir(parents=True, exist_ok=True)
    ir.write_text(json.dumps(world.model_dump(mode="json")), encoding="utf-8")

    first = runner.invoke(app, ["lint", str(ir), "--json"])
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout).get("skipped") is False

    second = runner.invoke(app, ["lint", str(ir), "--json"])
    assert second.exit_code == 0, second.output
    payload = json.loads(second.stdout)
    assert payload["skipped"] is True

    forced = runner.invoke(app, ["lint", str(ir), "--force", "--json"])
    assert forced.exit_code == 0, forced.output
    assert json.loads(forced.stdout).get("skipped") is False


def test_migrate_current_noop_and_unsupported(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    ir = tmp_path / "world.json"
    ir.write_text(json.dumps(world.model_dump(mode="json")), encoding="utf-8")

    ok = runner.invoke(app, ["migrate", str(ir), "--json"])
    assert ok.exit_code == 0, ok.output
    payload = json.loads(ok.stdout)
    assert payload["changed"] is False
    assert payload["to_version"] == world.ir_version

    bad = tmp_path / "old.json"
    bad.write_text(
        json.dumps({"ir_version": "9.9.9", "environment_id": "x", "name": "x"}),
        encoding="utf-8",
    )
    fail = runner.invoke(app, ["migrate", str(bad), "--json"])
    assert fail.exit_code != 0
    err = json.loads(fail.stdout)
    assert any(d["code"] == "EAC3004" for d in err["diagnostics"])


def test_import_merge_refund_decide_cli(tmp_path: Path) -> None:
    ws = tmp_path / "refund"
    init_workspace(ws, name="refund")
    src = REPO / "examples" / "refund" / "sources"
    for path in src.iterdir():
        (ws / "sources" / path.name).write_bytes(path.read_bytes())

    for kind, name in (
        ("openapi", "api.yaml"),
        ("procedure", "refund-sop.md"),
        ("traces", "trace-0187.jsonl"),
    ):
        result = runner.invoke(
            app,
            [
                "import",
                kind,
                str(ws / "sources" / name),
                "--path",
                str(ws),
                "--merge",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output

    facts = runner.invoke(app, ["facts", "--path", str(ws), "--reconcile", "--json"])
    # Open blocking ambiguities fail closed (non-zero) but still persist records.
    amb_path = ws / "facts" / "ambiguities.json"
    assert amb_path.is_file(), facts.output
    payload = json.loads(facts.stdout)
    ambs = payload.get("ambiguities") or payload.get("extra", {}).get("ambiguities")
    if ambs is None and "diagnostics" in payload:
        # Error envelope still carries extra when emit_report includes it.
        ambs = payload.get("ambiguities", [])
    # Prefer on-disk file as source of truth after fail-closed reconcile.
    disk = json.loads(amb_path.read_text(encoding="utf-8"))
    records = disk if isinstance(disk, list) else disk.get("ambiguities", disk)
    from envassure.reconciliation import ambiguity_id

    classic_id = ambiguity_id("action:submit_refund", "retry_behavior", "conflict")
    assert any(a["id"] == classic_id for a in records)
    assert not any(a["id"] == "AMB-0042" for a in records)

    decide = runner.invoke(
        app,
        [
            "decide",
            classic_id,
            "--path",
            str(ws),
            "-i",
            "timeout_then_retry_requires_idempotency_key",
            "-r",
            "domain_expert",
            "--rationale",
            "Align SOP retry with API by requiring idempotency keys.",
            "--json",
        ],
    )
    assert decide.exit_code == 0, decide.output
    amb = runner.invoke(app, ["ambiguities", "--path", str(ws), "--status", "all", "--json"])
    assert amb.exit_code == 0, amb.output
    statuses = {a["id"]: a["status"] for a in json.loads(amb.stdout)["ambiguities"]}
    assert statuses[classic_id] == "accepted"
