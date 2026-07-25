"""Expert decision records and ambiguity review helpers."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import AmbiguityRecord
from envassure.ir.primitives import AmbiguityStatus, ProvenanceRef


class DecisionRecord(BaseModel):
    """Expert decision resolving an ambiguity (§11.3)."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str
    ambiguity_id: str
    chosen_interpretation: str
    expert_role: str
    rationale: str
    timestamp: str
    provenance: ProvenanceRef = Field(default_factory=ProvenanceRef)
    residual_uncertainty: str | None = None
    status_effect: AmbiguityStatus = "accepted"


class ApplyDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DecisionRecord | None = None
    ambiguities: list[AmbiguityRecord] = Field(default_factory=list)
    diagnostics: DiagnosticReport = Field(default_factory=DiagnosticReport)


def list_ambiguities(
    ambiguities: Sequence[AmbiguityRecord],
    *,
    status: AmbiguityStatus | None = "open",
) -> list[AmbiguityRecord]:
    """Filter ambiguities by status (default: open only)."""
    items = list(ambiguities)
    if status is None:
        return sorted(items, key=lambda a: a.id)
    return sorted((a for a in items if a.status == status), key=lambda a: a.id)


def apply_decision(
    ambiguities: Sequence[AmbiguityRecord],
    *,
    ambiguity_id: str,
    chosen_interpretation: str,
    expert_role: str,
    rationale: str,
    decision_id: str | None = None,
    timestamp: str | None = None,
    provenance: ProvenanceRef | None = None,
    residual_uncertainty: str | None = None,
    status_effect: AmbiguityStatus = "accepted",
) -> ApplyDecisionResult:
    """Apply an expert decision, updating the matching ambiguity status."""
    report = DiagnosticReport()
    updated = [a.model_copy(deep=True) for a in ambiguities]
    target = next((a for a in updated if a.id == ambiguity_id), None)
    if target is None or target.status != "open":
        report.add(
            make_diagnostic(
                "EAC2004",
                ambiguity_id=ambiguity_id,
                subject=ambiguity_id,
            )
        )
        return ApplyDecisionResult(ambiguities=updated, diagnostics=report)

    ts = timestamp or datetime.now(UTC).isoformat()
    did = decision_id or f"DEC-{ambiguity_id}"
    decision = DecisionRecord(
        decision_id=did,
        ambiguity_id=ambiguity_id,
        chosen_interpretation=chosen_interpretation,
        expert_role=expert_role,
        rationale=rationale,
        timestamp=ts,
        provenance=provenance or ProvenanceRef(),
        residual_uncertainty=residual_uncertainty,
        status_effect=status_effect,
    )
    for index, amb in enumerate(updated):
        if amb.id == ambiguity_id:
            updated[index] = amb.model_copy(
                update={
                    "status": status_effect,
                    "decision_id": did,
                    "residual_uncertainty": residual_uncertainty,
                    "provenance": amb.provenance.model_copy(
                        update={
                            "decision_ids": list(dict.fromkeys([*amb.provenance.decision_ids, did]))
                        }
                    ),
                }
            )
            break
    return ApplyDecisionResult(
        decision=decision,
        ambiguities=updated,
        diagnostics=report,
    )


def save_decision(path: Path, decision: DecisionRecord, *, indent: int = 2) -> Path:
    """Write a decision JSON file (typically under ``decisions/``)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(decision.model_dump(mode="json"), indent=indent) + "\n",
        encoding="utf-8",
    )
    return path


def save_decision_under(
    decisions_dir: Path,
    decision: DecisionRecord,
    *,
    indent: int = 2,
) -> Path:
    """Save ``decisions/<decision_id>.json``."""
    target = decisions_dir / f"{decision.decision_id}.json"
    return save_decision(target, decision, indent=indent)


def load_decision(path: Path) -> DecisionRecord:
    data = json.loads(path.read_text(encoding="utf-8"))
    return DecisionRecord.model_validate(data)


def load_decisions_dir(decisions_dir: Path) -> list[DecisionRecord]:
    if not decisions_dir.is_dir():
        return []
    decisions: list[DecisionRecord] = []
    for path in sorted(decisions_dir.glob("*.json")):
        decisions.append(load_decision(path))
    return decisions


def save_ambiguities(path: Path, ambiguities: Sequence[AmbiguityRecord]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "ambiguities": [a.model_dump(mode="json") for a in ambiguities],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_ambiguities(path: Path) -> list[AmbiguityRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [AmbiguityRecord.model_validate(item) for item in raw]
    items = raw.get("ambiguities", [])
    return [AmbiguityRecord.model_validate(item) for item in items]
