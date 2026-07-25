"""EAC-R13 / R14 / R15: CEGR v2, proof obligations, concealed benchmarks."""

from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

from typer.testing import CliRunner

from envassure.benchmark.workflows import (
    WORKFLOW_IDS,
    build_workflow_oracle,
    oracle_digest_for,
    run_concealed_suite,
)
from envassure.cli.app import app
from envassure.obligations import (
    compile_proof_obligations,
    proof_obligation_pack_members,
    validate_proof_obligations,
)
from envassure.packaging import load_pack, save_pack
from envassure.reconciliation.cegr import (
    FIXTURE_AMBIGUITY_ALIASES,
    apply_cegr,
    counterexample_from_mapping,
    resolve_ambiguity_alias,
    run_cegr_loop,
)
from envassure.reconciliation.engine import ambiguity_id
from envassure.reports import build_assurance_case

runner = CliRunner()
REPO = Path(__file__).resolve().parents[1]


def _load_example(name: str):
    root = REPO / "examples" / name / "world.py"
    spec = importlib.util.spec_from_file_location(f"ex_{name}", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cegr_indeterminate_is_non_pass(tmp_path: Path) -> None:
    intake = counterexample_from_mapping(
        {
            "probe_id": "ind-1",
            "action_id": "approve",
            "overall_status": "indeterminate",
            "verdicts": [
                {
                    "dimension": "authorization",
                    "status": "indeterminate",
                    "detail": "missing auth evidence",
                }
            ],
            "minimized_sequence": ["approve"],
            "reference_outcome": {"authorized": True},
            "candidate_outcome": {},
        }
    )
    assert intake.overall_status == "indeterminate"
    assert "authorization" in intake.non_pass_dimensions()
    result = apply_cegr(intake, workspace_root=tmp_path, persist=True)
    assert any(d.code == "EAC7006" for d in result.diagnostics.diagnostics)
    assert result.generation.reconciliation.get("accepted_fact_ids") is not None
    # preferred may exist as review hint but accepted is the IR projection surface
    assert "preferred_fact_ids" in result.generation.reconciliation
    assert result.generation.closed is False


def test_cegr_loop_replay_before_after_and_close_on_evidence(tmp_path: Path) -> None:
    steps = ["approve", "observe"]

    def ref_exec(step: object) -> dict:
        return {"success": True, "authorized": True, "failure": None, "step": step}

    def cand_mismatch(step: object) -> dict:
        return {"success": False, "authorized": False, "failure": "forbidden", "step": step}

    open_loop = run_cegr_loop(
        {
            "probe_id": "loop-open",
            "action_id": "approve",
            "failing_dimensions": ["authorization"],
            "minimized_sequence": steps,
            "original_sequence": steps,
            "reference_outcome": {"authorized": True},
            "candidate_outcome": {"authorized": False},
        },
        workspace_root=tmp_path,
        persist=True,
        reference_execute=ref_exec,
        candidate_execute=cand_mismatch,
        fails=lambda seq: len(seq) >= 1,
    )
    assert open_loop.closed is False
    assert open_loop.replay_before is not None
    assert open_loop.replay_after is not None
    assert open_loop.replay_before.overall_status == "mismatch"
    assert open_loop.branch_apply is not None
    assert open_loop.branch_apply.requires_expert is True
    assert all(p.requires_expert for p in open_loop.result.transition_patches)
    assert open_loop.result.generation_dir is not None

    # Matching replay + no unresolved ambiguities can close.
    def cand_match(step: object) -> dict:
        return ref_exec(step)

    closed = run_cegr_loop(
        {
            "probe_id": "loop-close",
            "action_id": "approve",
            "overall_status": "match",
            "failing_dimensions": [],
            "minimized_sequence": ["approve"],
            "original_sequence": ["approve"],
            "reference_outcome": {"success": True, "authorized": True},
            "candidate_outcome": {"success": True, "authorized": True},
            "preserved_failure": False,
        },
        workspace_root=tmp_path,
        persist=True,
        reference_execute=ref_exec,
        candidate_execute=cand_match,
    )
    # No corrected facts → reconcile empty → no unresolved; replay matches → close.
    assert closed.replay_after is not None
    assert closed.replay_after.overall_status == "match"
    assert closed.closed is True
    assert any(d.code == "EAC7007" for d in closed.diagnostics.diagnostics)


def test_cegr_refund_alias_resolves_to_hashed_id() -> None:
    classic = ambiguity_id("action:submit_refund", "retry_behavior", "conflict")
    assert classic == "AMB-E224350D"
    assert resolve_ambiguity_alias("AMB-0042") == classic
    assert FIXTURE_AMBIGUITY_ALIASES["AMB-0042"] == classic
    # examples fixture alias stays in sync
    ex = _load_example("refund")
    assert ex.FIXTURE_AMBIGUITY_ALIASES["AMB-0042"] == classic


def test_proof_obligation_generators_and_pack(tmp_path: Path) -> None:
    world = _load_example("auth").build_auth_world()
    bundle = compile_proof_obligations(world)
    kinds = {o.claim_kind for o in bundle.obligations}
    assert "authorization_preservation" in kinds
    assert "observation_separation" in kinds
    assert "deterministic_reset_replay" in kinds
    assert "reward_trace_binding" in kinds
    assert "resource_conservation" in kinds
    assert "formal proof" not in bundle.disclaimer.lower() or "not" in bundle.disclaimer.lower()
    assert "does not constitute a completed formal proof" in bundle.disclaimer
    report = validate_proof_obligations(bundle, world=world)
    assert not report.has_errors()

    inv = _load_example("inventory").build_inventory_world()
    inv_bundle = compile_proof_obligations(inv)
    assert any(o.claim_kind == "resource_conservation" for o in inv_bundle.obligations)
    assert any(
        o.claim_kind == "deterministic_reset_replay" and o.mechanism_strength == "differential_evidence"
        for o in inv_bundle.obligations
    )

    case = build_assurance_case(world, proof_obligations=bundle)
    sec = case.section("20.9")
    assert sec is not None
    assert any(t.get("caption") == "Compiled proof obligations" for t in sec.tables)

    pack_path = tmp_path / "auth.eap"
    members = proof_obligation_pack_members(bundle)
    save_pack(pack_path, world, extra_files=members)
    _, _, raw = load_pack(pack_path)
    assert "obligations/proof-obligations.json" in raw
    with zipfile.ZipFile(pack_path) as zf:
        payload = json.loads(zf.read("obligations/proof-obligations.json"))
    assert payload["disclaimer"]
    assert len(payload["obligations"]) == len(bundle.obligations)


def test_concealed_benchmarks_probe_counts_and_negatives() -> None:
    for wid in WORKFLOW_IDS:
        oracle = build_workflow_oracle(wid, curated_count=100, generated_count=100, seed=0)
        assert len(oracle.episodes) == 200
        curated = [e for e in oracle.episodes if e.metadata.get("probe_kind") == "curated"]
        generated = [e for e in oracle.episodes if e.metadata.get("probe_kind") == "generated"]
        assert len(curated) == 100
        assert len(generated) == 100
        assert any(e.metadata.get("negative") for e in oracle.episodes)
        assert oracle.content_digest() == oracle_digest_for(wid, seed=0)

    # Manifest fixtures expand via generator
    for wid in WORKFLOW_IDS:
        path = REPO / "benchmarks" / "fixtures" / f"{wid}.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert raw["generator"] == wid
        assert raw["hidden_oracle_digest"] == oracle_digest_for(wid, seed=0)

    reports = run_concealed_suite(curated_count=20, generated_count=20, seed=0)
    assert len(reports) == 3
    for report in reports:
        assert report.episode_count == 40
        assert report.metrics.auth_agreement is not None
        assert report.metrics.failure_agreement is not None
        assert report.metadata.get("negative_probe_count", 0) > 0
        dims = report.metadata.get("dimension_metrics") or {}
        assert "leakage" in dims


def test_concealed_benchmark_cli() -> None:
    result = runner.invoke(app, ["benchmark", "--concealed", "--max-probes", "5", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert len(payload["reports"]) == 3
    for report in payload["reports"]:
        assert report["episode_count"] == 10  # 5 curated + 5 generated


def test_cegr_cli_loop(tmp_path: Path) -> None:
    intake_path = tmp_path / "ce.json"
    intake_path.write_text(
        json.dumps(
            {
                "probe_id": "cli-loop",
                "action_id": "increment",
                "failing_dimensions": ["state"],
                "overall_status": "mismatch",
                "minimized_sequence": ["increment"],
                "reference_outcome": {"state": {"value": 2}},
                "candidate_outcome": {"state": {"value": 3}},
            }
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["refine", str(intake_path), "--workspace", str(tmp_path), "--loop", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["closed"] is False
    assert "accepted_fact_ids" in payload
