"""Counterexample → reconciliation (CEGR) intake and refinement generations.

Stable intake types intentionally do **not** depend on differential engine
internals. Callers adapt differential outputs into ``CounterexampleIntake``
(or load fixture JSON) so CEGR remains usable while connectors evolve.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.models import AmbiguityRecord
from envassure.ir.primitives import EntityRef, ProvenanceRef
from envassure.reconciliation.engine import ReconciliationResult, reconcile

REFINEMENTS_DIRNAME = "refinements"

TransitionPatchKind = Literal[
    "add_guard",
    "update_effects",
    "mark_unsupported",
    "correct_failure",
    "correct_auth",
]


class DimensionMismatchIntake(BaseModel):
    """One typed dimension mismatch from differential comparison."""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    detail: str | None = None
    matched: bool = False


class CounterexampleIntake(BaseModel):
    """Stable CEGR intake document (fixture- and engine-agnostic)."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str
    action_id: str | None = None
    failing_dimensions: list[str] = Field(default_factory=list)
    dimension_details: list[DimensionMismatchIntake] = Field(default_factory=list)
    minimized_sequence: list[Any] = Field(default_factory=list)
    original_sequence: list[Any] = Field(default_factory=list)
    reference_outcome: dict[str, Any] = Field(default_factory=dict)
    candidate_outcome: dict[str, Any] = Field(default_factory=dict)
    subject: str | None = None
    notes: str | None = None
    preserved_failure: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class TransitionPatchProposal(BaseModel):
    """Proposed IR transition correction — never applied silently."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    kind: TransitionPatchKind
    proposal: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    transition_id: str | None = None
    requires_expert: bool = True


class RefinementGeneration(BaseModel):
    """One CEGR generation preserved under ``validation/refinements/``."""

    model_config = ConfigDict(extra="forbid")

    generation: int
    created_at: str
    intake_digest: str
    parent_digest: str | None = None
    probe_id: str
    ambiguities: list[AmbiguityRecord] = Field(default_factory=list)
    corrected_facts: list[SemanticFact] = Field(default_factory=list)
    transition_patches: list[TransitionPatchProposal] = Field(default_factory=list)
    reconciliation: dict[str, Any] = Field(default_factory=dict)
    diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class CegrResult(BaseModel):
    """Outcome of applying CEGR to an intake (+ optional existing facts)."""

    model_config = ConfigDict(extra="forbid")

    intake: CounterexampleIntake
    generation: RefinementGeneration
    ambiguities: list[AmbiguityRecord] = Field(default_factory=list)
    corrected_facts: list[SemanticFact] = Field(default_factory=list)
    transition_patches: list[TransitionPatchProposal] = Field(default_factory=list)
    reconciliation: ReconciliationResult = Field(default_factory=ReconciliationResult)
    diagnostics: DiagnosticReport = Field(default_factory=DiagnosticReport)
    generation_dir: str | None = None


def counterexample_from_mapping(data: dict[str, Any]) -> CounterexampleIntake:
    """Build intake from a plain dict (fixture or serialized differential output)."""
    failing = list(data.get("failing_dimensions") or [])
    details_raw = data.get("dimension_details") or data.get("verdicts") or []
    details: list[DimensionMismatchIntake] = []
    for item in details_raw:
        if isinstance(item, dict):
            dim = str(item.get("dimension") or item.get("name") or "")
            matched = bool(item.get("matched", False))
            if dim and (not matched or dim in failing):
                details.append(
                    DimensionMismatchIntake(
                        dimension=dim,
                        detail=item.get("detail") or item.get("confidence_note"),
                        matched=matched,
                    )
                )
                if dim not in failing and not matched:
                    failing.append(dim)
    minimized = data.get("minimized_sequence") or data.get("minimized") or []
    original = data.get("original_sequence") or data.get("original") or list(minimized)
    return CounterexampleIntake(
        probe_id=str(data.get("probe_id") or data.get("id") or "ce"),
        action_id=data.get("action_id"),
        failing_dimensions=failing,
        dimension_details=details,
        minimized_sequence=list(minimized),
        original_sequence=list(original),
        reference_outcome=dict(data.get("reference_outcome") or {}),
        candidate_outcome=dict(data.get("candidate_outcome") or {}),
        subject=data.get("subject"),
        notes=data.get("notes"),
        preserved_failure=bool(data.get("preserved_failure", True)),
        metadata=dict(data.get("metadata") or {}),
    )


def apply_cegr(
    intake: CounterexampleIntake | dict[str, Any],
    *,
    existing_facts: list[SemanticFact] | None = None,
    generation: int | None = None,
    parent_digest: str | None = None,
    workspace_root: Path | None = None,
    persist: bool = True,
) -> CegrResult:
    """Turn a counterexample into ambiguities, corrected facts, and transition patches.

    When ``workspace_root`` is set and ``persist`` is true, writes the generation
    under ``<workspace>/validation/refinements/gen-NNNN/``.
    """
    ce = intake if isinstance(intake, CounterexampleIntake) else counterexample_from_mapping(intake)
    report = DiagnosticReport()
    ambiguities: list[AmbiguityRecord] = []
    corrected: list[SemanticFact] = []
    patches: list[TransitionPatchProposal] = []

    action_id = ce.action_id or _infer_action_id(ce)
    subject = ce.subject or (f"action:{action_id}" if action_id else f"probe:{ce.probe_id}")

    if not ce.preserved_failure:
        report.add(
            make_diagnostic(
                "EAC7004",
                reason="intake preserved_failure is false; CEGR skipped mutation proposals",
                subject=ce.probe_id,
            )
        )

    amb = _ambiguity_from_intake(ce, subject=subject, action_id=action_id)
    ambiguities.append(amb)

    for dim in ce.failing_dimensions:
        fact = _corrected_fact_for_dimension(ce, dim, action_id=action_id)
        if fact is not None:
            corrected.append(fact)
        patch = _transition_patch_for_dimension(ce, dim, action_id=action_id)
        if patch is not None:
            patches.append(patch)

    merged_facts = list(existing_facts or []) + corrected
    recon = reconcile(merged_facts) if merged_facts else ReconciliationResult()
    # Prefer CEGR ambiguity; append recon ambiguities that are not duplicates.
    seen = {amb.id}
    for extra in recon.ambiguities:
        if extra.id not in seen:
            ambiguities.append(extra)
            seen.add(extra.id)

    report.extend(recon.diagnostics.diagnostics)
    report.add(
        make_diagnostic(
            "EAC7005",
            reason=(
                f"CEGR produced {len(ambiguities)} ambiguity(ies), "
                f"{len(corrected)} corrected fact(s), {len(patches)} patch(es) "
                f"for probe {ce.probe_id}"
            ),
            subject=ce.probe_id,
            details={
                "failing_dimensions": ce.failing_dimensions,
                "minimized_len": len(ce.minimized_sequence),
            },
        )
    )

    gen_num = generation if generation is not None else 1
    if workspace_root is not None:
        gen_num = generation if generation is not None else next_generation_number(workspace_root)

    generation_record = RefinementGeneration(
        generation=gen_num,
        created_at=datetime.now(UTC).isoformat(),
        intake_digest=ce.content_digest(),
        parent_digest=parent_digest,
        probe_id=ce.probe_id,
        ambiguities=ambiguities,
        corrected_facts=corrected,
        transition_patches=patches,
        reconciliation={
            "preferred_fact_ids": [f.fact_id for f in recon.preferred_facts],
            "superseded_fact_ids": list(recon.superseded_fact_ids),
            "ambiguity_ids": [a.id for a in recon.ambiguities],
        },
        diagnostics=[d.model_dump(mode="json") for d in report.diagnostics],
        metadata={"action_id": action_id, "subject": subject},
    )

    generation_dir: str | None = None
    if persist and workspace_root is not None:
        path = persist_refinement_generation(workspace_root, generation_record, intake=ce)
        generation_dir = str(path)

    return CegrResult(
        intake=ce,
        generation=generation_record,
        ambiguities=ambiguities,
        corrected_facts=corrected,
        transition_patches=patches,
        reconciliation=recon,
        diagnostics=report,
        generation_dir=generation_dir,
    )


def refinements_root(workspace_root: Path) -> Path:
    return Path(workspace_root) / "validation" / REFINEMENTS_DIRNAME


def next_generation_number(workspace_root: Path) -> int:
    root = refinements_root(workspace_root)
    if not root.is_dir():
        return 1
    highest = 0
    for child in root.iterdir():
        if child.is_dir() and child.name.startswith("gen-"):
            suffix = child.name.removeprefix("gen-")
            if suffix.isdigit():
                highest = max(highest, int(suffix))
    return highest + 1


def persist_refinement_generation(
    workspace_root: Path,
    generation: RefinementGeneration,
    *,
    intake: CounterexampleIntake | None = None,
) -> Path:
    """Write generation artifacts under ``validation/refinements/gen-NNNN/``."""
    root = refinements_root(workspace_root)
    target = root / f"gen-{generation.generation:04d}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "generation.json").write_text(
        json.dumps(generation.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    if intake is not None:
        (target / "intake.json").write_text(
            json.dumps(intake.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
    ambiguities_path = target / "ambiguities.json"
    ambiguities_path.write_text(
        json.dumps(
            [a.model_dump(mode="json") for a in generation.ambiguities],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    facts_path = target / "corrected_facts.json"
    facts_path.write_text(
        json.dumps(
            [f.model_dump(mode="json") for f in generation.corrected_facts],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    patches_path = target / "transition_patches.json"
    patches_path.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in generation.transition_patches],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Index for lineage.
    index_path = root / "index.json"
    index: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                index = loaded
        except json.JSONDecodeError:
            index = []
    index = [e for e in index if e.get("generation") != generation.generation]
    index.append(
        {
            "generation": generation.generation,
            "probe_id": generation.probe_id,
            "intake_digest": generation.intake_digest,
            "parent_digest": generation.parent_digest,
            "content_digest": generation.content_digest(),
            "path": f"gen-{generation.generation:04d}",
        }
    )
    index.sort(key=lambda e: int(e.get("generation", 0)))
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return target


def load_refinement_generation(path: Path) -> RefinementGeneration:
    data = json.loads((path / "generation.json").read_text(encoding="utf-8"))
    return RefinementGeneration.model_validate(data)


def list_refinement_generations(workspace_root: Path) -> list[RefinementGeneration]:
    root = refinements_root(workspace_root)
    if not root.is_dir():
        return []
    out: list[RefinementGeneration] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "generation.json").is_file():
            out.append(load_refinement_generation(child))
    return out


def _infer_action_id(ce: CounterexampleIntake) -> str | None:
    if ce.action_id:
        return ce.action_id
    for seq in (ce.minimized_sequence, ce.original_sequence):
        for step in seq:
            if isinstance(step, dict) and step.get("action_id"):
                return str(step["action_id"])
            if isinstance(step, str) and step and not step.startswith("probe:"):
                return step
    meta = ce.metadata
    action_meta = meta.get("action_id")
    if isinstance(action_meta, str):
        return action_meta
    return None


def _ambiguity_from_intake(
    ce: CounterexampleIntake,
    *,
    subject: str,
    action_id: str | None,
) -> AmbiguityRecord:
    dims = ce.failing_dimensions or ["unspecified"]
    excerpts = [
        f"probe={ce.probe_id}",
        f"failing_dimensions={dims}",
        f"minimized_sequence={ce.minimized_sequence!r}",
    ]
    if ce.notes:
        excerpts.append(ce.notes)
    for detail in ce.dimension_details:
        if detail.detail:
            excerpts.append(f"{detail.dimension}: {detail.detail}")
    interpretations = [f"align_candidate_to_reference:{dim}" for dim in dims] + [
        "widen_tolerance",
        "mark_unsupported_semantics",
        "expert_override",
    ]
    amb_id = f"AMB-CEGR-{canonical_hash({'probe': ce.probe_id, 'dims': dims})[:8].upper()}"
    return AmbiguityRecord(
        id=amb_id,
        subject=subject,
        source_excerpts=excerpts,
        conflict_class="differential_counterexample",
        candidate_interpretations=interpretations,
        default_prohibition=(
            "Do not claim differential validation until the counterexample is resolved."
        ),
        affected_actions=[action_id] if action_id else [],
        affected_analyses=["differential", "cegr"],
        operational_consequence=("Pack fidelity for mismatched dimensions remains unproven."),
        required_expert_role="environment_engineer",
        status="open",
        residual_uncertainty="; ".join(dims),
        provenance=ProvenanceRef(
            notes=f"cegr intake digest {ce.content_digest()[:16]}",
            source_ids=[f"probe:{ce.probe_id}"],
        ),
    )


def _corrected_fact_for_dimension(
    ce: CounterexampleIntake,
    dimension: str,
    *,
    action_id: str | None,
) -> SemanticFact | None:
    if not action_id:
        return None
    ref = ce.reference_outcome
    pred_map = {
        "failure": "failure_behavior",
        "authorization": "authorization",
        "retry": "retry_behavior",
        "idempotency": "idempotency",
        "success": "success_condition",
        "state": "state_effect",
        "observation": "observation_projection",
    }
    predicate = pred_map.get(dimension)
    if predicate is None:
        return None
    value: Any
    if dimension == "failure":
        value = ref.get("failure") or ref.get("failure_code") or {"aligned_to": "reference"}
    elif dimension == "authorization":
        value = {
            "authorized": ref.get("authorized", ref.get("success")),
            "source": "reference_connector",
        }
    elif dimension in {"retry", "idempotency"}:
        value = ref.get(dimension) or ref.get(f"{dimension}_behavior") or "reference_aligned"
    else:
        value = ref.get(dimension) or ref.get("observation") or ref.get("state") or "reference"
    fact_id = make_fact_id(
        subject_kind="action",
        subject_id=action_id,
        predicate=predicate,
        source=f"cegr:{ce.probe_id}",
        suffix=dimension,
    )
    return SemanticFact(
        fact_id=fact_id,
        subject=EntityRef(kind="action", id=action_id),
        predicate=predicate,
        value=value,
        source_refs=[f"cegr:{ce.probe_id}", f"dimension:{dimension}"],
        extraction_method="cegr_reference_alignment",
        confidence=ConfidenceRecord(
            evidence_class="executable_reference",
            extractor_certainty="high",
            conflict_status="unresolved",
            notes="Corrected candidate from differential reference outcome (CEGR).",
        ),
        status="candidate",
        kind_tags=["cegr", "corrected", dimension],
    )


def _transition_patch_for_dimension(
    ce: CounterexampleIntake,
    dimension: str,
    *,
    action_id: str | None,
) -> TransitionPatchProposal | None:
    if not action_id:
        return None
    kind_map: dict[str, TransitionPatchKind] = {
        "failure": "correct_failure",
        "authorization": "correct_auth",
        "state": "update_effects",
        "observation": "update_effects",
        "retry": "add_guard",
        "idempotency": "add_guard",
        "success": "update_effects",
    }
    kind = kind_map.get(dimension, "mark_unsupported")
    return TransitionPatchProposal(
        action_id=action_id,
        kind=kind,
        proposal={
            "dimension": dimension,
            "reference_outcome": ce.reference_outcome,
            "candidate_outcome": ce.candidate_outcome,
            "minimized_sequence": ce.minimized_sequence,
        },
        rationale=(
            f"Differential mismatch on {dimension} for probe {ce.probe_id}; "
            "align transition to reference or mark unsupported."
        ),
        requires_expert=True,
    )
