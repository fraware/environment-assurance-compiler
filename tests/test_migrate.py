"""Cross-minor IR migrate transforms and verify non-migration."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from envassure.cli.app import app
from envassure.ir.io import load_world, save_world
from envassure.ir.migrate import migrate_world_document
from envassure.ir.models import WorldDefinition
from envassure.ir.primitives import IR_PRIOR_STABLE, IR_VERSION, SUPPORTED_READ_VERSIONS
from envassure.ir.transforms import apply_transforms, transform_0_1_0_to_0_2_0
from envassure.ir.validate import validate_world
from envassure.packaging import save_pack, verify_pack

REPO = Path(__file__).resolve().parents[1]
FIXTURE_01 = REPO / "tests" / "fixtures" / "ir" / "world_0_1_0_minimal.json"
runner = CliRunner()


def test_supported_read_window_is_two_minors() -> None:
    assert IR_VERSION == "0.2.0"
    assert IR_PRIOR_STABLE == "0.1.0"
    assert "0.1.0" in SUPPORTED_READ_VERSIONS
    assert "0.2.0" in SUPPORTED_READ_VERSIONS
    assert len(SUPPORTED_READ_VERSIONS) == 2


def test_transform_0_1_to_0_2_additive_and_normalize() -> None:
    raw = json.loads(FIXTURE_01.read_text(encoding="utf-8"))
    assert raw["ir_version"] == "0.1.0"
    assert "assurance_profile" not in raw
    assert raw["state_model_version"] == "1"

    migrated, notes = apply_transforms(raw, "0.1.0", "0.2.0")
    assert migrated["ir_version"] == "0.2.0"
    assert migrated["assurance_profile"] == "baseline"
    assert migrated["state_model_version"] == "1.0"
    assert any("assurance_profile" in n for n in notes)
    assert any("state_model_version" in n for n in notes)

    world = WorldDefinition.model_validate(migrated)
    assert world.ir_version == IR_VERSION
    assert not validate_world(world).has_errors()


def test_transform_renames_deprecated_profile() -> None:
    payload = {
        "ir_version": "0.1.0",
        "environment_id": "x",
        "name": "X",
        "profile": "strict",
        "state_model_version": "1",
    }
    out = transform_0_1_0_to_0_2_0(payload)
    assert out["assurance_profile"] == "strict"
    assert "profile" not in out


def test_migrate_round_trip_fixture(tmp_path: Path) -> None:
    src = tmp_path / "world.json"
    src.write_text(FIXTURE_01.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "world_0_2.json"
    result = migrate_world_document(src, output=out, dry_run=False)
    assert result.changed is True
    assert result.from_version == "0.1.0"
    assert result.to_version == "0.2.0"
    assert result.world is not None
    assert result.world.assurance_profile == "baseline"
    assert result.world.state_model_version == "1.0"
    assert any(d.code == "EAC3005" for d in result.report.diagnostics)
    assert not result.report.has_errors()

    loaded = load_world(out)
    assert loaded.ir_version == "0.2.0"
    assert loaded.assurance_profile == "baseline"


def test_migrate_dry_run_does_not_write(tmp_path: Path) -> None:
    src = tmp_path / "world.json"
    src.write_text(FIXTURE_01.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "should_not_exist.json"
    result = migrate_world_document(src, output=out, dry_run=True)
    assert result.changed is True
    assert not out.exists()
    assert any("dry-run" in n for n in result.notes)


def test_migrate_identity_noop_current(tmp_path: Path) -> None:
    world = WorldDefinition(environment_id="cur", name="Current")
    path = tmp_path / "cur.json"
    save_world(path, world)
    result = migrate_world_document(path)
    assert result.changed is False
    assert result.from_version == IR_VERSION
    assert any("no-op" in n or "identity" in n for n in result.notes)


def test_migrate_refuses_unknown_version(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"ir_version": "9.9.9", "environment_id": "x", "name": "x"}),
        encoding="utf-8",
    )
    result = migrate_world_document(bad)
    assert result.changed is False
    assert result.report.has_errors()
    assert any(d.code == "EAC3004" for d in result.report.diagnostics)


def test_migrate_cli_0_1_to_0_2(tmp_path: Path) -> None:
    src = tmp_path / "world.json"
    src.write_bytes(FIXTURE_01.read_bytes())
    result = runner.invoke(app, ["migrate", str(src), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    assert payload["from_version"] == "0.1.0"
    assert payload["to_version"] == "0.2.0"
    loaded = json.loads(src.read_text(encoding="utf-8"))
    assert loaded["ir_version"] == "0.2.0"
    assert loaded["assurance_profile"] == "baseline"


def test_verify_pack_never_auto_migrates(tmp_path: Path) -> None:
    """Packs built from 0.1.0-shaped docs verify without rewriting IR."""
    raw = json.loads(FIXTURE_01.read_text(encoding="utf-8"))
    # Load via migrate path only for a valid 0.2 world to package; separately
    # ensure verify_pack does not invoke migrate (no ir rewrite side effects).
    world = WorldDefinition.model_validate(
        apply_transforms(raw, "0.1.0", "0.2.0")[0]
    )
    pack_path = tmp_path / "fixture.eap"
    save_pack(pack_path, world)
    before = pack_path.read_bytes()
    report = verify_pack(pack_path)
    assert not report.has_errors(), report.diagnostics
    assert pack_path.read_bytes() == before
    # No migrate diagnostics on verify.
    assert not any(d.code in {"EAC3005", "EAC3006"} for d in report.diagnostics)


def test_load_0_1_fixture_without_migrate_fills_defaults() -> None:
    """Read window accepts 0.1.0; Pydantic fills additive defaults in memory only."""
    world = load_world(FIXTURE_01)
    assert world.ir_version == "0.1.0"
    assert world.assurance_profile == "baseline"
    # Disk unchanged.
    disk = json.loads(FIXTURE_01.read_text(encoding="utf-8"))
    assert "assurance_profile" not in disk
