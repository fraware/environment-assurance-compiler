"""Focused tests for Milestone A release scripts (fail-closed gates)."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(
    script: str, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )


def test_check_tag_version_match() -> None:
    proc = _run("check_tag_version.py", "--tag", "v0.2.0.dev0", "--version", "0.2.0.dev0")
    assert proc.returncode == 0, proc.stderr
    assert "matches" in proc.stdout


def test_check_tag_version_mismatch_fails_closed() -> None:
    proc = _run("check_tag_version.py", "--tag", "v0.2.0b1", "--version", "0.2.0.dev0")
    assert proc.returncode == 1
    assert "mismatch" in proc.stderr.lower()


def test_check_tag_version_rejects_non_v_prefix() -> None:
    proc = _run("check_tag_version.py", "--tag", "0.2.0.dev0", "--version", "0.2.0.dev0")
    assert proc.returncode == 1


def test_check_tag_version_allow_untagged() -> None:
    import os

    env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_REF")}
    proc = _run("check_tag_version.py", "--allow-untagged", env=env)
    assert proc.returncode == 0


def test_write_sha256sums_and_manifest(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "envassure-0.2.0.dev0-py3-none-any.whl"
    sdist = dist / "envassure-0.2.0.dev0.tar.gz"
    payload = b"wheel-bytes"
    wheel.write_bytes(payload)
    sdist.write_bytes(b"sdist-bytes")

    proc = _run("write_sha256sums.py", str(dist), "--out", str(dist / "SHA-256SUMS"))
    assert proc.returncode == 0, proc.stderr
    sums = (dist / "SHA-256SUMS").read_text(encoding="utf-8")
    assert hashlib.sha256(payload).hexdigest() in sums

    commit = "a" * 40
    proc = _run(
        "generate_release_manifest.py",
        "--dist-dir",
        str(dist),
        "--tag",
        "v0.2.0.dev0",
        "--commit",
        commit,
        "--release-version",
        "0.2.0.dev0",
        "--out",
        str(dist / "release-manifest.json"),
    )
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads((dist / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["release_version"] == "0.2.0.dev0"
    assert manifest["artifacts"]["wheel"]["sha256"] == hashlib.sha256(payload).hexdigest()
    assert manifest["known_limitations"]


def test_generate_release_manifest_rejects_bad_commit(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "envassure-0.2.0.dev0-py3-none-any.whl").write_bytes(b"w")
    (dist / "envassure-0.2.0.dev0.tar.gz").write_bytes(b"s")
    proc = _run(
        "generate_release_manifest.py",
        "--dist-dir",
        str(dist),
        "--tag",
        "v0.2.0.dev0",
        "--commit",
        "notasha",
        "--release-version",
        "0.2.0.dev0",
        "--out",
        str(dist / "release-manifest.json"),
    )
    assert proc.returncode == 1


def test_release_manifest_schema_loads() -> None:
    path = ROOT / "schemas" / "release-manifest-1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["properties"]["schema_version"]["const"] == 1


@pytest.mark.parametrize(
    "script",
    [
        "check_tag_version.py",
        "generate_release_manifest.py",
        "check_package_acceptance.py",
        "write_sha256sums.py",
        "verify_repro_bundle.py",
    ],
)
def test_scripts_are_executable_modules(script: str) -> None:
    assert (SCRIPTS / script).is_file()
