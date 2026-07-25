"""Workspace layout, configuration, sources, and lock files."""

from __future__ import annotations

from envassure.workspace.config import WorkspaceConfig, load_workspace_config
from envassure.workspace.doctor import DoctorResult, run_doctor
from envassure.workspace.incremental import (
    IncrementalDecision,
    decide_incremental_lint,
    decide_incremental_rebuild,
    digest_workspace_sources,
    record_build_state,
    record_lint_state,
)
from envassure.workspace.init import InitResult, init_workspace
from envassure.workspace.layout import WORKSPACE_DIRS, WORKSPACE_FILES, WorkspacePaths
from envassure.workspace.lock import (
    BuildState,
    LockFile,
    PluginLockFile,
    load_build_state,
    load_lock,
    load_plugin_lock,
    write_default_locks,
)
from envassure.workspace.sources import (
    AUTHORITY_CLASSES,
    AuthorityClass,
    CompletenessDeclaration,
    ConfidentialityClass,
    SourceArtifact,
    SourcesManifest,
    load_sources_manifest,
    save_sources_manifest,
)

__all__ = [
    "AUTHORITY_CLASSES",
    "WORKSPACE_DIRS",
    "WORKSPACE_FILES",
    "AuthorityClass",
    "BuildState",
    "CompletenessDeclaration",
    "ConfidentialityClass",
    "DoctorResult",
    "IncrementalDecision",
    "InitResult",
    "LockFile",
    "PluginLockFile",
    "SourceArtifact",
    "SourcesManifest",
    "WorkspaceConfig",
    "WorkspacePaths",
    "decide_incremental_lint",
    "decide_incremental_rebuild",
    "digest_workspace_sources",
    "init_workspace",
    "load_build_state",
    "load_lock",
    "load_plugin_lock",
    "load_sources_manifest",
    "load_workspace_config",
    "record_build_state",
    "record_lint_state",
    "run_doctor",
    "save_sources_manifest",
    "write_default_locks",
]
