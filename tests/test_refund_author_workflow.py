"""DoD: external-author refund path — import through verify-pack + fidelity ledger."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from envassure.cli.app import app
from envassure.fidelity import FidelityLedger
from envassure.packaging import PACK_MEMBER_FIDELITY, load_pack
from envassure.reconciliation import ambiguity_id
from envassure.workspace.init import init_workspace

runner = CliRunner()
REPO = Path(__file__).resolve().parents[1]
DECIDED_WORLD = REPO / "tests" / "fixtures" / "author" / "refund_decided_world.py"
REFUND_SOURCES = REPO / "examples" / "refund" / "input"


def test_refund_external_author_build_verify_workflow(tmp_path: Path) -> None:
    """Automate the documented author sequence on examples/refund sources."""
    ws = tmp_path / "refund"
    init_workspace(ws, name="refund")
    for path in REFUND_SOURCES.iterdir():
        if path.is_file():
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
    amb_path = ws / "facts" / "ambiguities.json"
    assert amb_path.is_file(), facts.output
    classic_id = ambiguity_id("action:submit_refund", "retry_behavior", "conflict")
    disk = json.loads(amb_path.read_text(encoding="utf-8"))
    records = disk if isinstance(disk, list) else disk.get("ambiguities", [])
    assert any(a["id"] == classic_id for a in records)

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
    assert list((ws / "decisions").glob("*.json")), "decision artifact missing"

    # Author projects the decision into IR via a workspace world.py.
    shutil.copy(DECIDED_WORLD, ws / "world.py")
    build = runner.invoke(app, ["build-ir", "--path", str(ws), "--force", "--json"])
    assert build.exit_code == 0, build.output
    ir_path = ws / "ir" / "world.json"
    assert ir_path.is_file()
    world_doc = json.loads(ir_path.read_text(encoding="utf-8"))
    assert world_doc["environment_id"] == "refund.v1"
    action = next(a for a in world_doc["actions"] if a["id"] == "submit_refund")
    assert action["retry_behavior"] == "timeout_then_retry_requires_idempotency_key"
    amb = next(a for a in world_doc["ambiguities"] if a["id"] == classic_id)
    assert amb["status"] == "accepted"

    pack_path = ws / "pack.eap"
    ledger_path = ws / "fidelity-ledger.json"
    custom_ledger = {
        "schema_version": "1",
        "environment_id": "refund.v1",
        "claims": [
            {
                "claim": "Refund retry decision is expert-reviewed under fixture sources.",
                "scope": {
                    "environment_id": "refund.v1",
                    "element_ids": ["action:submit_refund"],
                    "dimension": "retry_behavior",
                },
                "evidence": ["decision:workspace"],
                "coverage": "refund author workflow",
                "reviewer": "domain_expert",
                "known_gaps": [],
                "status": "expert_reviewed",
            }
        ],
        "metadata": {},
    }
    ledger_path.write_text(json.dumps(custom_ledger, indent=2) + "\n", encoding="utf-8")
    migration_path = ws / "migration.json"
    migration_path.write_text(
        json.dumps(
            {
                "from_version": "0.2.0",
                "to_version": "0.2.0",
                "steps": [],
                "notes": ["author workflow identity migrate"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    sig_path = ws / "author.sig"
    sig_path.write_bytes(b"refund-author-detached-sig\n")

    packaged = runner.invoke(
        app,
        [
            "package",
            str(ir_path),
            "-o",
            str(pack_path),
            "--profile",
            "authoring",
            "--fidelity",
            str(ledger_path),
            "--sources-manifest",
            str(ws / "sources.yml"),
            "--migration-history",
            str(migration_path),
            "--signature",
            str(sig_path),
            "--workspace",
            str(ws),
            "--json",
        ],
    )
    assert packaged.exit_code == 0, packaged.output

    verified = runner.invoke(app, ["verify-pack", str(pack_path), "--json"])
    assert verified.exit_code == 0, verified.output

    _manifest, loaded_world, members = load_pack(pack_path)
    assert PACK_MEMBER_FIDELITY in members
    ledger = FidelityLedger.model_validate(json.loads(members[PACK_MEMBER_FIDELITY]))
    assert ledger.environment_id == loaded_world.environment_id == "refund.v1"
    assert ledger.claims, "pack must include fidelity ledger entries"
    assert all(c.scope.environment_id == "refund.v1" for c in ledger.claims)
    assert any(c.status == "expert_reviewed" for c in ledger.claims)
    assert "signatures/author.sig" in members
    sources = json.loads(members["sources/manifest.json"])
    assert sources.get("schema_version") == 1
    migration = json.loads(members["migration/history.json"])
    assert migration["notes"] == ["author workflow identity migrate"]
    statuses = {c.status for c in ledger.claims}
    assert statuses <= {
        "unassessed",
        "structurally_valid",
        "trace_supported",
        "expert_reviewed",
        "empirically_compared",
    }
