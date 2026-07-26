"""EAC-08: pack format v2 adversarial verification gates."""

from __future__ import annotations

import importlib.util
import json
import struct
import warnings
import zipfile
from pathlib import Path

import pytest

from envassure.canonical import sha256_hex
from envassure.packaging import (
    MAX_COMPRESSION_RATIO,
    PACK_FORMAT_VERSION,
    PACK_MEMBER_COMPATIBILITY,
    PACK_MEMBER_FIDELITY,
    PACK_MEMBER_MANIFEST,
    PACK_MEMBER_PROVENANCE,
    PACK_MEMBER_WORLD,
    PackManifest,
    save_pack,
    verify_pack,
    write_raw_zip,
)


def _load_example(name: str):
    root = Path(__file__).resolve().parents[1] / "examples" / name / "world.py"
    spec = importlib.util.spec_from_file_location(f"ex_{name}", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pack_v2_required_members_and_versions(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    pack_path = tmp_path / "counter.eap"
    manifest = save_pack(pack_path, world)
    assert manifest.format_version == PACK_FORMAT_VERSION == "2"
    assert manifest.runtime_version
    assert manifest.policy_version
    report = verify_pack(pack_path)
    assert not report.has_errors(), report.diagnostics
    with zipfile.ZipFile(pack_path, "r") as zf:
        names = set(zf.namelist())
    for required in (
        PACK_MEMBER_WORLD,
        "schemas/world.json",
        "sources/manifest.json",
        "provenance/bundle.json",
        "migration/history.json",
        PACK_MEMBER_COMPATIBILITY,
        PACK_MEMBER_FIDELITY,
    ):
        assert required in names


def test_zip_slip_rejected(tmp_path: Path) -> None:
    evil = tmp_path / "slip.eap"
    write_raw_zip(
        evil,
        {
            PACK_MEMBER_MANIFEST: b'{"format_version":"2"}\n',
            "../evil.txt": b"pwned\n",
            "ir/../../outside.txt": b"nope\n",
        },
    )
    report = verify_pack(evil)
    assert report.has_errors()
    assert any("unsafe" in d.summary.lower() or ".." in d.summary for d in report.diagnostics)


def test_absolute_path_member_rejected(tmp_path: Path) -> None:
    evil = tmp_path / "abs.eap"
    # Craft local header with absolute-looking name via ZipInfo.
    with zipfile.ZipFile(evil, "w", compression=zipfile.ZIP_STORED) as zf:
        info = zipfile.ZipInfo("/tmp/evil.txt")
        zf.writestr(info, b"x")
        zf.writestr(PACK_MEMBER_MANIFEST, b"{}\n")
    report = verify_pack(evil)
    assert report.has_errors()
    assert any(
        "unsafe" in d.summary.lower() or "absolute" in d.summary.lower() for d in report.diagnostics
    )


def test_duplicate_zip_entry_names_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dup.eap"
    # Build via append so namelist can contain duplicates.
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr(PACK_MEMBER_MANIFEST, b'{"format_version":"2"}\n')
        zf.writestr("ir/world.json", b'{"a":1}\n')
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(path, "a", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("ir/world.json", b'{"a":2}\n')
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
    if names.count("ir/world.json") < 2:
        pytest.skip("ZipFile append collapsed duplicate names on this platform")
    report = verify_pack(path)
    assert report.has_errors()
    assert any("duplicate" in d.summary.lower() for d in report.diagnostics)


def test_decompression_bomb_ratio_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bomb.eap"
    # Highly compressible payload: large uncompressed, tiny compressed.
    payload = b"\x00" * (2 * 1024 * 1024)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PACK_MEMBER_MANIFEST, b'{"format_version":"2"}\n')
        zf.writestr("bomb.bin", payload)
    with zipfile.ZipFile(path, "r") as zf:
        info = zf.getinfo("bomb.bin")
        ratio = info.file_size / max(info.compress_size, 1)
    if ratio <= MAX_COMPRESSION_RATIO:
        pytest.skip(f"platform compression ratio {ratio:.1f} below limit")
    report = verify_pack(path)
    assert report.has_errors()
    assert any(
        "ratio" in d.summary.lower() or "uncompressed" in d.summary.lower()
        for d in report.diagnostics
    )


def test_tampered_member_bytes_and_content_digest(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    pack_path = tmp_path / "ok.eap"
    save_pack(pack_path, world)

    # Tamper a member while keeping the ZIP structure.
    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    members[PACK_MEMBER_WORLD] = members[PACK_MEMBER_WORLD] + b" "
    tampered = tmp_path / "tampered.eap"
    write_raw_zip(tampered, members)
    report = verify_pack(tampered)
    assert report.has_errors()
    assert any("checksum" in d.summary.lower() for d in report.diagnostics)

    # Tamper content_digest only.
    digest_tampered = tmp_path / "digest.eap"
    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    manifest = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    manifest.content_digest = "0" * 64
    members[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    write_raw_zip(digest_tampered, members)
    report2 = verify_pack(digest_tampered)
    assert report2.has_errors()
    assert any("content_digest" in d.summary.lower() for d in report2.diagnostics)


def test_unsupported_format_and_ir_versions_fail_closed(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    pack_path = tmp_path / "base.eap"
    save_pack(pack_path, world)
    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}

    bad_fmt = tmp_path / "bad_fmt.eap"
    manifest = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    manifest.format_version = "99"
    manifest.recompute_content_digest()
    members_fmt = dict(members)
    members_fmt[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    write_raw_zip(bad_fmt, members_fmt)
    report = verify_pack(bad_fmt)
    assert report.has_errors()
    assert any("format_version" in d.summary for d in report.diagnostics)

    bad_ir = tmp_path / "bad_ir.eap"
    manifest2 = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    manifest2.ir_version = "9.9.9"
    manifest2.recompute_content_digest()
    members_ir = dict(members)
    members_ir[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest2.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    write_raw_zip(bad_ir, members_ir)
    report_ir = verify_pack(bad_ir)
    assert report_ir.has_errors()
    assert any("ir_version" in d.summary for d in report_ir.diagnostics)


def test_manifest_file_hash_list_covers_members(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    pack_path = tmp_path / "hashed.eap"
    manifest = save_pack(pack_path, world)
    with zipfile.ZipFile(pack_path, "r") as zf:
        for entry in manifest.files:
            data = zf.read(entry.path)
            assert sha256_hex(data) == entry.sha256
            assert len(data) == entry.size


def test_crafted_zip_slip_via_raw_local_header(tmp_path: Path) -> None:
    """Ensure path traversal names are rejected even if ZipInfo tricks are used."""
    path = tmp_path / "crafted.eap"
    # Minimal valid ZIP with a traversal filename in the central directory.
    filename = b"../../tmp/pwn.txt"
    data = b"pwn\n"
    local = (
        b"PK\x03\x04"
        + struct.pack("<HHHHHIIIHH", 20, 0, 0, 0, 0, 0, len(data), len(data), len(filename), 0)
        + filename
        + data
    )
    central = (
        b"PK\x01\x02"
        + struct.pack(
            "<HHHHHHIIIHHHHHII",
            20,
            20,
            0,
            0,
            0,
            0,
            0,
            len(data),
            len(data),
            len(filename),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        + filename
    )
    end = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, 1, 1, len(central), len(local), 0)
    path.write_bytes(local + central + end)
    report = verify_pack(path)
    assert report.has_errors()


def test_optional_signatures_must_be_manifest_listed(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    sig = tmp_path / "pack.sig"
    sig.write_bytes(b"detached-sig\n")
    pack_path = tmp_path / "signed.eap"
    save_pack(pack_path, world, extra_files={"signatures/pack.sig": sig.read_bytes()})
    report = verify_pack(pack_path)
    assert not report.has_errors(), report.diagnostics

    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    manifest = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    assert isinstance(manifest.metadata.get("signatures"), dict)
    assert manifest.metadata["signatures"]["members"][0]["path"] == "signatures/pack.sig"

    # Drop signature from manifest.files while leaving the ZIP member.
    manifest.files = [e for e in manifest.files if not e.path.startswith("signatures/")]
    manifest.recompute_content_digest()
    members[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    evil = tmp_path / "sig_unlisted.eap"
    write_raw_zip(evil, members)
    report_bad = verify_pack(evil)
    assert report_bad.has_errors()
    assert any("signature" in d.summary.lower() for d in report_bad.diagnostics)


def test_signature_metadata_rejects_digest_and_inventory_mismatch(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    sig = tmp_path / "pack.sig"
    sig.write_bytes(b"detached-sig\n")
    pack_path = tmp_path / "signed.eap"
    save_pack(pack_path, world, extra_files={"signatures/pack.sig": sig.read_bytes()})

    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    manifest = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    # Tamper opaque signature bytes but keep manifest.files hash in sync so we
    # hit metadata.signatures digest mismatch specifically.
    members["signatures/pack.sig"] = b"tampered-sig\n"
    for entry in manifest.files:
        if entry.path == "signatures/pack.sig":
            entry.sha256 = sha256_hex(members["signatures/pack.sig"])
            entry.size = len(members["signatures/pack.sig"])
    # Leave metadata.signatures.members digest pointing at the original bytes.
    manifest.recompute_content_digest()
    members[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    evil = tmp_path / "sig_meta_mismatch.eap"
    write_raw_zip(evil, members)
    report = verify_pack(evil)
    assert report.has_errors()
    assert any("signature digest mismatch" in d.summary.lower() for d in report.diagnostics)


def test_verify_pack_rejects_missing_required_member_even_if_checksums_match(
    tmp_path: Path,
) -> None:
    world = _load_example("counter").build_counter_world()
    pack_path = tmp_path / "base.eap"
    save_pack(pack_path, world)
    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    del members[PACK_MEMBER_PROVENANCE]
    manifest = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    manifest.files = [e for e in manifest.files if e.path != PACK_MEMBER_PROVENANCE]
    manifest.recompute_content_digest()
    members[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    evil = tmp_path / "missing_prov.eap"
    write_raw_zip(evil, members)
    report = verify_pack(evil)
    assert report.has_errors()
    assert any("provenance" in d.summary.lower() for d in report.diagnostics)


def test_invalid_fidelity_ledger_rejected(tmp_path: Path) -> None:
    world = _load_example("counter").build_counter_world()
    pack_path = tmp_path / "base.eap"
    save_pack(pack_path, world)
    with zipfile.ZipFile(pack_path, "r") as zf:
        members = {n: zf.read(n) for n in zf.namelist() if not n.endswith("/")}
    members[PACK_MEMBER_FIDELITY] = (
        b'{"environment_id":"counter.v1","claims":[],"metadata":{"score":1}}\n'
    )
    # Fix manifest hash for the tampered member so we hit ledger schema, not checksum.
    manifest = PackManifest.model_validate(json.loads(members[PACK_MEMBER_MANIFEST]))
    for entry in manifest.files:
        if entry.path == PACK_MEMBER_FIDELITY:
            entry.sha256 = sha256_hex(members[PACK_MEMBER_FIDELITY])
            entry.size = len(members[PACK_MEMBER_FIDELITY])
    manifest.recompute_content_digest()
    members[PACK_MEMBER_MANIFEST] = (
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"
    ).encode("utf-8")
    bad = tmp_path / "bad_ledger.eap"
    write_raw_zip(bad, members)
    report = verify_pack(bad)
    assert report.has_errors()
    assert any("fidelity" in d.summary.lower() for d in report.diagnostics)
