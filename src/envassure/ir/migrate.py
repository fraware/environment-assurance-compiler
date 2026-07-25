"""Explicit IR schema migration (never silent on verify)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.io import save_world
from envassure.ir.models import WorldDefinition
from envassure.ir.primitives import IR_VERSION, SUPPORTED_READ_VERSIONS
from envassure.ir.transforms import apply_transforms

# Re-export for callers that historically imported from this module.
__all__ = [
    "SUPPORTED_READ_VERSIONS",
    "MigrateResult",
    "migrate_world_document",
    "read_ir_version",
]


@dataclass(slots=True)
class MigrateResult:
    """Outcome of an explicit ``eac migrate`` invocation."""

    changed: bool
    from_version: str
    to_version: str
    world: WorldDefinition | None = None
    report: DiagnosticReport = field(default_factory=DiagnosticReport)
    notes: list[str] = field(default_factory=list)


def read_ir_version(path: Path) -> tuple[dict[str, Any], str | None]:
    """Load raw IR JSON and return ``(payload, ir_version_or_None)``."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("IR document must be a JSON object")
    version = raw.get("ir_version")
    if version is None:
        return raw, None
    if not isinstance(version, str):
        raise ValueError("ir_version must be a string")
    return raw, version


def migrate_world_document(
    path: Path,
    *,
    output: Path | None = None,
    dry_run: bool = False,
) -> MigrateResult:
    """Upgrade an IR document to the compiler's current ``IR_VERSION``.

    Already-current documents are a documented no-op (identity). Unsupported
    versions fail closed (no write). Verification paths must never call this
    implicitly.
    """
    report = DiagnosticReport()
    try:
        payload, from_version = read_ir_version(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report.add(
            make_diagnostic(
                "EAC3001",
                reason=f"cannot read IR for migrate: {exc}",
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version="unknown",
            to_version=IR_VERSION,
            report=report,
        )

    if from_version is None:
        report.add(
            make_diagnostic(
                "EAC3004",
                version="(missing)",
                current=IR_VERSION,
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version="missing",
            to_version=IR_VERSION,
            report=report,
        )

    if from_version == IR_VERSION:
        try:
            world = WorldDefinition.model_validate(payload)
        except Exception as exc:
            report.add(
                make_diagnostic(
                    "EAC3001",
                    reason=f"current IR failed validation: {exc}",
                    subject=str(path),
                )
            )
            return MigrateResult(
                changed=False,
                from_version=from_version,
                to_version=IR_VERSION,
                report=report,
            )
        report.add(
            make_diagnostic(
                "EAC3005",
                version=from_version,
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version=from_version,
            to_version=IR_VERSION,
            world=world,
            report=report,
            notes=["already at current ir_version; identity/no-op; no write"],
        )

    if from_version not in SUPPORTED_READ_VERSIONS:
        report.add(
            make_diagnostic(
                "EAC3004",
                version=from_version,
                current=IR_VERSION,
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version=from_version,
            to_version=IR_VERSION,
            report=report,
        )

    try:
        migrated, transform_notes = apply_transforms(payload, from_version, IR_VERSION)
    except KeyError as exc:
        report.add(
            make_diagnostic(
                "EAC3006",
                from_version=from_version,
                to_version=IR_VERSION,
                reason=str(exc),
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version=from_version,
            to_version=IR_VERSION,
            report=report,
        )
    except Exception as exc:
        report.add(
            make_diagnostic(
                "EAC3006",
                from_version=from_version,
                to_version=IR_VERSION,
                reason=f"transform failed: {exc}",
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version=from_version,
            to_version=IR_VERSION,
            report=report,
        )

    try:
        world = WorldDefinition.model_validate(migrated)
    except Exception as exc:
        report.add(
            make_diagnostic(
                "EAC3001",
                reason=f"migrated document failed validation: {exc}",
                subject=str(path),
            )
        )
        return MigrateResult(
            changed=False,
            from_version=from_version,
            to_version=IR_VERSION,
            report=report,
            notes=transform_notes,
        )

    out = output or path
    if not dry_run:
        save_world(out, world)
    report.add(
        make_diagnostic(
            "EAC3005",
            version=f"{from_version}->{IR_VERSION}",
            subject=str(out),
        )
    )
    notes = list(transform_notes)
    notes.append(f"wrote {out}" if not dry_run else "dry-run; no write")
    return MigrateResult(
        changed=True,
        from_version=from_version,
        to_version=IR_VERSION,
        world=world,
        report=report,
        notes=notes,
    )
