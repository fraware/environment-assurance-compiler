"""Workspace and toolchain health checks (`eac doctor`)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from envassure import __version__
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.workspace.config import load_workspace_config
from envassure.workspace.layout import WorkspacePaths
from envassure.workspace.lock import check_lock_consistency, load_lock
from envassure.workspace.sources import load_sources_manifest

MIN_PYTHON = (3, 11)


@dataclass
class DoctorCheck:
    name: str
    ok: bool
    detail: str


@dataclass
class DoctorResult:
    report: DiagnosticReport
    checks: list[DoctorCheck] = field(default_factory=list)
    network_enabled: bool = False

    @property
    def ok(self) -> bool:
        return not self.report.has_errors()


def run_doctor(
    root: Path | None = None,
    *,
    network: bool = False,
) -> DoctorResult:
    """Check Python, workspace layout, lock consistency; network opt-in only."""
    report = DiagnosticReport()
    checks: list[DoctorCheck] = []
    result = DoctorResult(report=report, checks=checks, network_enabled=network)

    py_ok = sys.version_info[:2] >= MIN_PYTHON
    checks.append(
        DoctorCheck(
            name="python",
            ok=py_ok,
            detail=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    if not py_ok:
        report.add(
            make_diagnostic(
                "EAC9002",
                version=f"{sys.version_info.major}.{sys.version_info.minor}",
                minimum=f"{MIN_PYTHON[0]}.{MIN_PYTHON[1]}",
            )
        )

    checks.append(
        DoctorCheck(name="envassure", ok=True, detail=__version__),
    )

    for extra, module_name in (
        ("gym", "gymnasium"),
        ("pettingzoo", "pettingzoo"),
        ("postgres", "psycopg"),
        ("model-assisted", "httpx"),
    ):
        installed = _module_available(module_name)
        checks.append(
            DoctorCheck(
                name=f"extra:{extra}",
                ok=True,  # missing extras are warnings, not hard failures
                detail="installed" if installed else "not installed",
            )
        )
        if not installed:
            report.add(make_diagnostic("EAC9003", extra=extra))

    if not network:
        report.add(make_diagnostic("EAC9004"))
        checks.append(DoctorCheck(name="network", ok=True, detail="skipped (pass --network)"))
    else:
        checks.append(
            DoctorCheck(
                name="network",
                ok=True,
                detail="enabled (no remote probes registered in Phase 0)",
            )
        )

    if root is not None:
        paths = WorkspacePaths(root=root.resolve())
        missing = paths.missing_required()
        if missing:
            for item in missing:
                report.add(
                    make_diagnostic(
                        "EAC8001",
                        path=item,
                        subject=str(paths.root),
                        affected_artifacts=[item],
                    )
                )
            checks.append(
                DoctorCheck(
                    name="workspace",
                    ok=False,
                    detail=f"missing: {', '.join(missing)}",
                )
            )
            return result

        try:
            config = load_workspace_config(paths.eac_toml)
            checks.append(
                DoctorCheck(
                    name="eac.toml",
                    ok=True,
                    detail=f"project={config.project.name} ir={config.project.ir_version}",
                )
            )
            spec = SpecifierSet(config.compiler.require)
            if Version(__version__) not in spec:
                report.add(
                    make_diagnostic(
                        "EAC8003",
                        reason=(
                            f"compiler {__version__} does not satisfy "
                            f"require={config.compiler.require!r}"
                        ),
                        subject=str(paths.eac_toml),
                    )
                )
                checks[-1] = DoctorCheck(
                    name="eac.toml",
                    ok=False,
                    detail="compiler requirement not satisfied",
                )
        except Exception as exc:
            report.add(
                make_diagnostic(
                    "EAC8003",
                    reason=str(exc),
                    subject=str(paths.eac_toml),
                )
            )
            checks.append(DoctorCheck(name="eac.toml", ok=False, detail=str(exc)))

        try:
            manifest = load_sources_manifest(paths.sources_yml)
            checks.append(
                DoctorCheck(
                    name="sources.yml",
                    ok=True,
                    detail=f"{len(manifest.sources)} source(s)",
                )
            )
            source_digests = manifest.digests()
        except Exception as exc:
            report.add(
                make_diagnostic(
                    "EAC8003",
                    reason=str(exc),
                    subject=str(paths.sources_yml),
                )
            )
            checks.append(DoctorCheck(name="sources.yml", ok=False, detail=str(exc)))
            source_digests = {}

        if paths.lock_json.is_file():
            try:
                lock = load_lock(paths.lock_json)
                reasons = check_lock_consistency(
                    lock,
                    source_digests=source_digests,
                    compiler_version=__version__,
                )
                if reasons:
                    for reason in reasons:
                        report.add(make_diagnostic("EAC8004", reason=reason))
                    checks.append(
                        DoctorCheck(
                            name="lock",
                            ok=False,
                            detail="; ".join(reasons),
                        )
                    )
                else:
                    checks.append(
                        DoctorCheck(
                            name="lock",
                            ok=True,
                            detail=f"compiler={lock.compiler_version}",
                        )
                    )
            except Exception as exc:
                report.add(make_diagnostic("EAC8004", reason=str(exc)))
                checks.append(DoctorCheck(name="lock", ok=False, detail=str(exc)))
        else:
            report.add(
                make_diagnostic(
                    "EAC8001",
                    path=".eac/lock.json",
                    subject=str(paths.root),
                )
            )
            checks.append(DoctorCheck(name="lock", ok=False, detail="missing"))

    return result


def _module_available(name: str) -> bool:
    try:
        __import__(name)
    except ImportError:
        return False
    return True
