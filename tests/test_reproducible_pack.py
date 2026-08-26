"""Cross-interpreter reproducible .eap archive invariants."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from envassure.packaging import PACK_MEMBER_MANIFEST, load_pack, save_pack, verify_pack


def _counter_world():
    import importlib.util

    root = Path(__file__).resolve().parents[1] / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("ex_counter_repro", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_counter_world()


def test_source_date_epoch_makes_pack_byte_reproducible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1704067200")
    world = _counter_world()
    first = tmp_path / "first.eap"
    second = tmp_path / "second.eap"

    manifest_a = save_pack(first, world)
    manifest_b = save_pack(second, world)

    assert first.read_bytes() == second.read_bytes()
    assert manifest_a == manifest_b
    assert manifest_a.created_at == "2024-01-01T00:00:00+00:00"
    assert not verify_pack(first).has_errors()

    loaded, _, _ = load_pack(first)
    assert loaded.content_digest == manifest_a.content_digest
    with zipfile.ZipFile(first, "r") as zf:
        assert zf.namelist()[0] == PACK_MEMBER_MANIFEST
        for info in zf.infolist():
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED
            assert info.create_system == 3
            assert (info.external_attr >> 16) & 0o777 == 0o644
            assert info.extra == b""
            assert info.comment == b""


def test_invalid_source_date_epoch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "not-an-integer")
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        save_pack(tmp_path / "bad.eap", _counter_world())

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "-1")
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        save_pack(tmp_path / "negative.eap", _counter_world())
