"""Unit tests for research benchmark pack lint/verify (eac pack)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from envassure.benchmark.pack_format import (
    compute_pack_tree_digest,
    inspect_benchmark_pack,
    lint_benchmark_pack,
    load_pack_manifest,
    reproduce_benchmark_pack,
    verify_benchmark_pack,
)

REPO = Path(__file__).resolve().parents[1]
PACKS = REPO / "packs"
SAMPLE = PACKS / "envassure-transactional-refund"


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="benchmark packs not present")
def test_shipped_packs_lint_and_verify() -> None:
    for pack_dir in sorted(p for p in PACKS.iterdir() if p.is_dir()):
        lint = lint_benchmark_pack(pack_dir)
        assert not lint.has_errors(), lint.diagnostics
        verify = verify_benchmark_pack(pack_dir)
        assert not verify.has_errors(), verify.diagnostics
        manifest = load_pack_manifest(pack_dir / "pack.yaml")
        assert manifest.pack_id == pack_dir.name
        assert manifest.digests.hidden_oracle
        assert manifest.digests.pack_tree == compute_pack_tree_digest(pack_dir)


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="benchmark packs not present")
def test_pack_lint_detects_missing_include(tmp_path: Path) -> None:
    dest = tmp_path / SAMPLE.name
    shutil.copytree(SAMPLE, dest)
    (dest / "sources" / "conflict.yaml").unlink()
    report = lint_benchmark_pack(dest)
    assert report.has_errors()
    assert any("conflict.yaml" in d.summary for d in report.diagnostics)


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="benchmark packs not present")
def test_pack_verify_detects_baseline_digest_tamper(tmp_path: Path) -> None:
    dest = tmp_path / SAMPLE.name
    shutil.copytree(SAMPLE, dest)
    baseline = dest / "baselines" / "public-baseline.json"
    text = baseline.read_text(encoding="utf-8")
    baseline.write_text(text.replace('"EF-0"', '"EF-1"'), encoding="utf-8")
    report = verify_benchmark_pack(dest)
    assert report.has_errors()
    assert any("baseline_world digest mismatch" in d.summary for d in report.diagnostics)


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="benchmark packs not present")
def test_pack_inspect_and_reproduce(tmp_path: Path) -> None:
    info = inspect_benchmark_pack(SAMPLE)
    assert info.manifest.pack_id == "envassure-transactional-refund"
    assert info.member_count > 5
    receipt = reproduce_benchmark_pack(SAMPLE, output_dir=tmp_path)
    assert receipt["ok"] is True
    assert (tmp_path / "envassure-transactional-refund-reproduce.json").is_file()


def test_invalid_pack_yaml_fails_lint(tmp_path: Path) -> None:
    pack = tmp_path / "bad-pack"
    pack.mkdir()
    (pack / "pack.yaml").write_text("schema_version: '9'\npack_id: x\n", encoding="utf-8")
    for name in ("LICENSE", "README.md", "data-card.md", "benchmark-card.md"):
        (pack / name).write_text("x\n", encoding="utf-8")
    for dirname in (
        "sources",
        "decisions",
        "world",
        "tasks",
        "probes",
        "baselines",
        "expected-public",
        "schemas",
    ):
        (pack / dirname).mkdir()
    report = lint_benchmark_pack(pack)
    assert report.has_errors()


def test_manifest_round_trip_yaml(tmp_path: Path) -> None:
    pytest.importorskip("yaml")
    if not SAMPLE.is_dir():
        pytest.skip("benchmark packs not present")
    manifest = load_pack_manifest(SAMPLE / "pack.yaml")
    out = tmp_path / "pack.yaml"
    out.write_text(
        yaml.safe_dump(manifest.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    again = load_pack_manifest(out)
    assert again.pack_id == manifest.pack_id
    assert again.digests.hidden_oracle == manifest.digests.hidden_oracle
