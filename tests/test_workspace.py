"""Tests for workspace init, sources, and lock model."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from envassure import __version__
from envassure.workspace.config import load_workspace_config
from envassure.workspace.init import init_workspace
from envassure.workspace.layout import WORKSPACE_DIRS, WorkspacePaths
from envassure.workspace.lock import (
    LockFile,
    check_lock_consistency,
    load_lock,
    write_default_locks,
)
from envassure.workspace.sources import (
    AUTHORITY_CLASSES,
    CompletenessDeclaration,
    ConfidentialityClass,
    SourceArtifact,
    SourcesManifest,
    load_sources_manifest,
)


def test_init_creates_tree(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    result = init_workspace(target, name="demo")
    assert not result.report.has_errors()
    paths = result.paths
    assert paths.eac_toml.is_file()
    assert paths.sources_yml.is_file()
    assert paths.lock_json.is_file()
    assert paths.plugin_lock_json.is_file()
    assert paths.build_state_json.is_file()
    for dirname in WORKSPACE_DIRS:
        assert (target / dirname).is_dir()
    config = load_workspace_config(paths.eac_toml)
    assert config.project.name == "demo"
    manifest = load_sources_manifest(paths.sources_yml)
    assert manifest.sources == []
    lock = load_lock(paths.lock_json)
    assert lock.compiler_version == __version__
    assert lock.source_digests == {}


def test_init_refuses_existing(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    first = init_workspace(target)
    assert not first.report.has_errors()
    second = init_workspace(target)
    assert second.report.has_errors()
    assert second.report.diagnostics[0].code == "EAC8002"


def test_init_force(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    init_workspace(target, name="a")
    result = init_workspace(target, name="b", force=True)
    assert not result.report.has_errors()
    assert load_workspace_config(result.paths.eac_toml).project.name == "b"


def test_source_artifact_requires_locator() -> None:
    with pytest.raises(ValidationError):
        SourceArtifact(
            source_id="s1",
            kind="openapi",
            digest="abc",
            acquired_at=datetime.now(tz=UTC),
            authority="api_contract",
        )


def test_source_artifact_authority_vocabulary() -> None:
    assert "model_proposal" in AUTHORITY_CLASSES
    art = SourceArtifact(
        source_id="api",
        kind="openapi",
        path="sources/api.yaml",
        digest="deadbeef",
        acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
        authority="api_contract",
        confidentiality=ConfidentialityClass.INTERNAL,
        completeness=CompletenessDeclaration.PARTIAL,
        parser="openapi",
        parser_version="3.1",
    )
    assert art.path == "sources/api.yaml"
    manifest = SourcesManifest(sources=[art])
    assert manifest.digests() == {"api": "deadbeef"}


def test_lock_consistency(tmp_path: Path) -> None:
    eac = tmp_path / ".eac"
    write_default_locks(eac, source_digests={"api": "aaa"})
    lock = load_lock(eac / "lock.json")
    assert (
        check_lock_consistency(lock, source_digests={"api": "aaa"}, compiler_version=__version__)
        == []
    )
    reasons = check_lock_consistency(
        lock, source_digests={"api": "bbb"}, compiler_version=__version__
    )
    assert reasons and "digest mismatch" in reasons[0]


def test_lock_content_digest_stable() -> None:
    lock = LockFile(compiler_version="0.1.0a0", source_digests={"a": "1"})
    assert (
        lock.content_digest()
        == LockFile(compiler_version="0.1.0a0", source_digests={"a": "1"}).content_digest()
    )


def test_workspace_paths_missing(tmp_path: Path) -> None:
    paths = WorkspacePaths(root=tmp_path)
    assert not paths.is_workspace()
    assert "eac.toml" in paths.missing_required()
