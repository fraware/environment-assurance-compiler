"""Create a new EnvAssure authoring workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic, DiagnosticReport
from envassure.workspace.config import (
    ProjectSection,
    WorkspaceConfig,
    write_workspace_config,
)
from envassure.workspace.layout import WORKSPACE_DIRS, WorkspacePaths
from envassure.workspace.lock import write_default_locks
from envassure.workspace.sources import SourcesManifest, save_sources_manifest


@dataclass(frozen=True, slots=True)
class InitResult:
    paths: WorkspacePaths
    created: list[str]
    report: DiagnosticReport


def init_workspace(
    root: Path,
    *,
    name: str | None = None,
    force: bool = False,
) -> InitResult:
    """Create the standard workspace tree. Fail closed if already present."""
    root = root.resolve()
    paths = WorkspacePaths(root=root)
    report = DiagnosticReport()
    created: list[str] = []

    if paths.eac_toml.exists() and not force:
        report.add(
            make_diagnostic(
                "EAC8002",
                path=str(paths.eac_toml),
                subject=str(root),
                affected_artifacts=[str(paths.eac_toml)],
            )
        )
        return InitResult(paths=paths, created=created, report=report)

    project_name = name or root.name or "environment"
    try:
        root.mkdir(parents=True, exist_ok=True)
        for dirname in WORKSPACE_DIRS:
            directory = root / dirname
            directory.mkdir(parents=True, exist_ok=True)
            created.append(str(directory.relative_to(root)).replace("\\", "/") + "/")
            gitkeep = directory / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.write_text("", encoding="utf-8")
                created.append(str(gitkeep.relative_to(root)).replace("\\", "/"))

        config = WorkspaceConfig(project=ProjectSection(name=project_name))
        write_workspace_config(paths.eac_toml, config)
        created.append("eac.toml")

        manifest = SourcesManifest(sources=[])
        save_sources_manifest(paths.sources_yml, manifest)
        created.append("sources.yml")

        write_default_locks(paths.eac_dir, source_digests={})
        for lock_name in ("lock.json", "plugin-lock.json", "build-state.json"):
            created.append(f".eac/{lock_name}")

        readme = root / "README.md"
        if not readme.exists() or force:
            readme.write_text(
                _workspace_readme(project_name),
                encoding="utf-8",
            )
            created.append("README.md")
    except OSError as exc:
        diag: Diagnostic = make_diagnostic(
            "EAC8005",
            path=str(root),
            reason=str(exc),
            subject=str(root),
        )
        report.add(diag)
        return InitResult(paths=paths, created=created, report=report)

    return InitResult(paths=paths, created=created, report=report)


def _workspace_readme(name: str) -> str:
    return (
        f"# {name}\n\n"
        "EnvAssure authoring workspace.\n\n"
        "## Layout\n\n"
        "- `eac.toml` — project and compiler settings\n"
        "- `sources.yml` — SourceArtifact manifest\n"
        "- `sources/` — local source files\n"
        "- `facts/` — semantic facts\n"
        "- `decisions/` — expert decisions\n"
        "- `ir/` — Environment Assurance IR\n"
        "- `generated/` — generated runtime and tests\n"
        "- `validation/` — validation evidence\n"
        "- `reports/` — assurance reports\n"
        "- `.eac/` — lock and build state\n\n"
        "Run `eac doctor` to verify the toolchain.\n"
    )
