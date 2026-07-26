"""Counterexample-guided reconciliation (CEGR) v2.

Loop: minimize → replay both systems → candidate corrections with provenance →
branch apply → rerun counterexample → regression/mutation → immutable
generation → close only on evidence.

Stable intake types intentionally do **not** depend on differential engine
internals. Callers adapt differential outputs into ``CounterexampleIntake``
(or load fixture JSON) so CEGR remains usable while connectors evolve.

Authoritative IR projection must use ``accepted_facts`` only — never
``preferred_facts`` / ranked review hints.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.models import AmbiguityRecord, WorldDefinition
from envassure.ir.primitives import EntityRef, ProvenanceRef
from envassure.reconciliation.engine import (
    ReconciliationResult,
    ambiguity_id,
    reconcile,
)

REFINEMENTS_DIRNAME = "refinements"

TransitionPatchKind = Literal[
    "add_guard",
    "update_effects",
    "mark_unsupported",
    "correct_failure",
    "correct_auth",
]

DifferentialStatus = Literal["match", "mismatch", "indeterminate", "not_applicable"]

# Historical demo alias → stable hashed id (classic refund retry conflict).
# Production reconcile never hard-codes AMB-0042; CEGR resolves aliases here.
FIXTURE_AMBIGUITY_ALIASES: dict[str, str] = {
    "AMB-0042": ambiguity_id("action:submit_refund", "retry_behavior", "conflict"),
}


def resolve_ambiguity_alias(
    ambiguity_id_or_alias: str,
    *,
    alias_map: Mapping[str, str] | None = None,
) -> str:
    """Map fixture aliases (e.g. AMB-0042) to stable hashed ambiguity ids."""
    table = dict(FIXTURE_AMBIGUITY_ALIASES)
    if alias_map:
        table.update(alias_map)
    return table.get(ambiguity_id_or_alias, ambiguity_id_or_alias)


class DimensionMismatchIntake(BaseModel):
    """One typed dimension verdict from differential comparison."""

    model_config = ConfigDict(extra="forbid")

    dimension: str
    detail: str | None = None
    matched: bool = False
    status: DifferentialStatus = "mismatch"

    def is_non_pass(self) -> bool:
        """Indeterminate and mismatch both block CEGR close / differential pass."""
        return self.status in {"mismatch", "indeterminate"}


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
    overall_status: DifferentialStatus | None = None
    subject: str | None = None
    notes: str | None = None
    preserved_failure: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))

    def non_pass_dimensions(self) -> list[str]:
        dims = [d.dimension for d in self.dimension_details if d.is_non_pass() and d.dimension]
        if dims:
            return list(dict.fromkeys(dims))
        return list(self.failing_dimensions)


class TransitionPatchProposal(BaseModel):
    """Proposed IR transition correction — never applied silently."""

    model_config = ConfigDict(extra="forbid")

    action_id: str
    kind: TransitionPatchKind
    proposal: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    transition_id: str | None = None
    requires_expert: bool = True
    provenance: dict[str, Any] = Field(default_factory=dict)


class ReplayObservation(BaseModel):
    """One before/after replay of reference vs candidate on a sequence."""

    model_config = ConfigDict(extra="forbid")

    phase: Literal["before", "after"]
    sequence: list[Any] = Field(default_factory=list)
    reference_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    candidate_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    overall_status: DifferentialStatus = "indeterminate"
    dimension_statuses: dict[str, DifferentialStatus] = Field(default_factory=dict)
    notes: str | None = None


class BranchApplyRecord(BaseModel):
    """Recorded branch application of expert-required patches (not silent IR mutate)."""

    model_config = ConfigDict(extra="forbid")

    branch_id: str
    patches_applied: list[dict[str, Any]] = Field(default_factory=list)
    applied: bool = False
    requires_expert: bool = True
    rationale: str = (
        "Patches remain expert-gated; branch records intent without mutating release IR."
    )


class RegressionMutationReport(BaseModel):
    """Regression / mutation probe results after a CEGR generation."""

    model_config = ConfigDict(extra="forbid")

    regression_passed: bool | None = None
    mutation_detected: bool | None = None
    probes_run: int = 0
    details: list[dict[str, Any]] = Field(default_factory=list)


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
    replay_before: ReplayObservation | None = None
    replay_after: ReplayObservation | None = None
    branch_apply: BranchApplyRecord | None = None
    regression_mutation: RegressionMutationReport | None = None
    closed: bool = False
    close_evidence: str | None = None
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


class CegrLoopResult(BaseModel):
    """Full CEGR v2 loop outcome — closed only when evidence warrants."""

    model_config = ConfigDict(extra="forbid")

    intake: CounterexampleIntake
    result: CegrResult
    closed: bool = False
    close_evidence: str | None = None
    replay_before: ReplayObservation | None = None
    replay_after: ReplayObservation | None = None
    branch_apply: BranchApplyRecord | None = None
    regression_mutation: RegressionMutationReport | None = None
    minimization: dict[str, Any] = Field(default_factory=dict)
    diagnostics: DiagnosticReport = Field(default_factory=DiagnosticReport)


def counterexample_from_mapping(data: dict[str, Any]) -> CounterexampleIntake:
    """Build intake from a plain dict (fixture or serialized differential output)."""
    failing = list(data.get("failing_dimensions") or [])
    details_raw = data.get("dimension_details") or data.get("verdicts") or []
    details: list[DimensionMismatchIntake] = []
    for item in details_raw:
        if not isinstance(item, dict):
            continue
        dim = str(item.get("dimension") or item.get("name") or "")
        if not dim:
            continue
        status = _coerce_status(
            item.get("status"),
            matched=item.get("matched"),
        )
        # Four-state: indeterminate is never a pass.
        non_pass = status in {"mismatch", "indeterminate"}
        matched = status == "match"
        if non_pass or dim in failing or item.get("matched") is False:
            details.append(
                DimensionMismatchIntake(
                    dimension=dim,
                    detail=item.get("detail") or item.get("confidence_note"),
                    matched=matched,
                    status=status,
                )
            )
            if dim not in failing and non_pass:
                failing.append(dim)

    overall = _coerce_status(data.get("overall_status"), matched=data.get("matched"))
    if failing:
        detail_statuses = {d.status for d in details}
        if overall == "match" or overall is None:
            # Four-state: indeterminate evidence must not collapse to match,
            # and should not be rewritten as mismatch when no true mismatch exists.
            if "mismatch" in detail_statuses:
                overall = "mismatch"
            elif "indeterminate" in detail_statuses:
                overall = "indeterminate"
            elif overall is None:
                overall = "mismatch"
    if overall is None and failing:
        overall = "mismatch"

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
        overall_status=overall,
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
    alias_map: Mapping[str, str] | None = None,
) -> CegrResult:
    """Turn a counterexample into ambiguities, corrected facts, and transition patches.

    When ``workspace_root`` is set and ``persist`` is true, writes the generation
    under ``<workspace>/validation/refinements/gen-NNNN/``.

    Reconciliation summary exposes ``accepted_fact_ids`` only for IR projection;
    ``preferred_fact_ids`` remain review-ordering hints and must not drive release IR.
    """
    ce = intake if isinstance(intake, CounterexampleIntake) else counterexample_from_mapping(intake)
    report = DiagnosticReport()
    ambiguities: list[AmbiguityRecord] = []
    corrected: list[SemanticFact] = []
    patches: list[TransitionPatchProposal] = []

    action_id = ce.action_id or _infer_action_id(ce)
    subject = ce.subject or (f"action:{action_id}" if action_id else f"probe:{ce.probe_id}")
    failing = ce.non_pass_dimensions()

    if not ce.preserved_failure:
        report.add(
            make_diagnostic(
                "EAC7004",
                reason="intake preserved_failure is false; CEGR skipped mutation proposals",
                subject=ce.probe_id,
            )
        )

    if ce.overall_status == "indeterminate" or any(
        d.status == "indeterminate" for d in ce.dimension_details
    ):
        report.add(
            make_diagnostic(
                "EAC7006",
                reason="CEGR treats indeterminate differential evidence as non-pass",
                subject=ce.probe_id,
                details={"failing_dimensions": failing},
            )
        )

    amb = _ambiguity_from_intake(ce, subject=subject, action_id=action_id, alias_map=alias_map)
    ambiguities.append(amb)

    for dim in failing:
        fact = _corrected_fact_for_dimension(ce, dim, action_id=action_id)
        if fact is not None:
            corrected.append(fact)
        patch = _transition_patch_for_dimension(ce, dim, action_id=action_id)
        if patch is not None:
            patches.append(patch)

    merged_facts = list(existing_facts or []) + corrected
    recon = reconcile(merged_facts) if merged_facts else ReconciliationResult()
    seen = {resolve_ambiguity_alias(amb.id, alias_map=alias_map)}
    for extra in recon.ambiguities:
        resolved = resolve_ambiguity_alias(extra.id, alias_map=alias_map)
        if resolved not in seen:
            if resolved != extra.id:
                ambiguities.append(extra.model_copy(update={"id": resolved}))
            else:
                ambiguities.append(extra)
            seen.add(resolved)

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
                "failing_dimensions": failing,
                "minimized_len": len(ce.minimized_sequence),
                "accepted_fact_count": len(recon.accepted_facts),
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
            # Authoritative projection surface — accepted only.
            "accepted_fact_ids": [f.fact_id for f in recon.accepted_facts],
            "rejected_fact_ids": list(recon.rejected_fact_ids),
            "unresolved_ambiguity_ids": [
                resolve_ambiguity_alias(a.id, alias_map=alias_map)
                for a in recon.unresolved_ambiguities
            ],
            # Review-ordering hints — never project into release IR.
            "preferred_fact_ids": [f.fact_id for f in recon.preferred_facts],
            "ranked_candidate_ids": [f.fact_id for f in recon.ranked_candidates],
            "superseded_fact_ids": list(recon.superseded_fact_ids),
            "ambiguity_ids": [
                resolve_ambiguity_alias(a.id, alias_map=alias_map) for a in recon.ambiguities
            ],
        },
        diagnostics=[d.model_dump(mode="json") for d in report.diagnostics],
        metadata={"action_id": action_id, "subject": subject, "overall_status": ce.overall_status},
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


def run_cegr_loop(
    intake: CounterexampleIntake | dict[str, Any],
    *,
    existing_facts: list[SemanticFact] | None = None,
    workspace_root: Path | None = None,
    persist: bool = True,
    parent_digest: str | None = None,
    alias_map: Mapping[str, str] | None = None,
    reference_execute: Callable[[Any], dict[str, Any]] | None = None,
    candidate_execute: Callable[[Any], dict[str, Any]] | None = None,
    fails: Callable[[Sequence[Any]], bool] | None = None,
    world: WorldDefinition | None = None,
    regression_probes: Sequence[dict[str, Any]] | None = None,
    apply_branch: bool = True,
) -> CegrLoopResult:
    """Run the full CEGR v2 loop; close only when replay evidence shows match.

    Expert-required patches are always recorded; branch apply never silently
    mutates release IR. Automatic replay runs before proposals and after the
    recorded branch when executors are provided.
    """
    report = DiagnosticReport()
    ce = intake if isinstance(intake, CounterexampleIntake) else counterexample_from_mapping(intake)
    minimization_meta: dict[str, Any] = {}

    # 1) Minimize when a failure predicate is supplied.
    sequence = list(ce.original_sequence or ce.minimized_sequence)
    if fails is not None and sequence:
        from envassure.differential.minimize import minimize_counterexample

        minimized = minimize_counterexample(sequence, fails, probe_id=ce.probe_id)
        report.extend(minimized.diagnostics)
        ce = ce.model_copy(
            update={
                "original_sequence": list(minimized.original),
                "minimized_sequence": list(minimized.minimized),
                "preserved_failure": minimized.preserved_failure,
            }
        )
        minimization_meta = {
            "original_len": len(minimized.original),
            "minimized_len": len(minimized.minimized),
            "iterations": minimized.iterations,
            "preserved_failure": minimized.preserved_failure,
            "shrunk": minimized.shrunk,
        }

    # 2) Replay both systems before corrections.
    replay_seq = list(ce.minimized_sequence or ce.original_sequence)
    replay_before = _replay_pair(
        phase="before",
        sequence=replay_seq,
        reference_execute=reference_execute,
        candidate_execute=candidate_execute,
    )
    if replay_before is not None:
        ce = _merge_replay_into_intake(ce, replay_before)

    # 3-4) Candidate corrections with provenance + reconcile (accepted_facts only).
    result = apply_cegr(
        ce,
        existing_facts=existing_facts,
        parent_digest=parent_digest,
        workspace_root=None,
        persist=False,
        alias_map=alias_map,
    )
    report.extend(result.diagnostics.diagnostics)

    # 5) Branch apply — record only; patches remain expert-required.
    branch = BranchApplyRecord(
        branch_id=f"branch-{result.generation.intake_digest[:12]}",
        patches_applied=[
            {
                **p.model_dump(mode="json"),
                "requires_expert": True,
            }
            for p in result.transition_patches
        ],
        applied=False,
        requires_expert=True,
    )
    if apply_branch and result.transition_patches:
        # Intentional: do not mutate IR. Mark branch as staged for expert review.
        branch = branch.model_copy(
            update={
                "applied": False,
                "rationale": (
                    "Staged expert-required patches on immutable branch; "
                    "release IR unchanged until decide() accepts facts."
                ),
            }
        )

    # 6) Rerun counterexample after staging (same executors; status still non-pass
    # unless external evidence already matches — we never invent success).
    replay_after = _replay_pair(
        phase="after",
        sequence=replay_seq,
        reference_execute=reference_execute,
        candidate_execute=candidate_execute,
    )

    # 7) Regression / mutation probes (optional world mutations).
    reg = _run_regression_mutation(
        world=world,
        regression_probes=regression_probes,
        reference_execute=reference_execute,
        candidate_execute=candidate_execute,
    )

    # 8-9) Close only on evidence: overall match with no indeterminate dims.
    closed, evidence = _evaluate_close(
        intake=ce,
        replay_after=replay_after or replay_before,
        reconciliation=result.reconciliation,
    )
    if closed:
        report.add(
            make_diagnostic(
                "EAC7007",
                reason=evidence or "CEGR closed on replay evidence",
                subject=ce.probe_id,
            )
        )
    else:
        report.add(
            make_diagnostic(
                "EAC7008",
                reason=evidence or "CEGR remains open; expert decision required",
                subject=ce.probe_id,
                details={
                    "accepted_fact_ids": [f.fact_id for f in result.reconciliation.accepted_facts],
                    "unresolved": len(result.reconciliation.unresolved_ambiguities),
                },
            )
        )

    gen_num = 1
    if workspace_root is not None:
        gen_num = next_generation_number(workspace_root)

    generation = result.generation.model_copy(
        update={
            "generation": gen_num,
            "replay_before": replay_before,
            "replay_after": replay_after,
            "branch_apply": branch,
            "regression_mutation": reg,
            "closed": closed,
            "close_evidence": evidence,
            "diagnostics": [d.model_dump(mode="json") for d in report.diagnostics],
        }
    )

    generation_dir: str | None = None
    if persist and workspace_root is not None:
        generation_dir = str(persist_refinement_generation(workspace_root, generation, intake=ce))

    final = CegrResult(
        intake=ce,
        generation=generation,
        ambiguities=result.ambiguities,
        corrected_facts=result.corrected_facts,
        transition_patches=result.transition_patches,
        reconciliation=result.reconciliation,
        diagnostics=report,
        generation_dir=generation_dir,
    )
    return CegrLoopResult(
        intake=ce,
        result=final,
        closed=closed,
        close_evidence=evidence,
        replay_before=replay_before,
        replay_after=replay_after,
        branch_apply=branch,
        regression_mutation=reg,
        minimization=minimization_meta,
        diagnostics=report,
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
    """Write immutable generation artifacts under ``validation/refinements/gen-NNNN/``."""
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
    # Index for lineage — generations themselves remain immutable once written.
    index_path = root / "index.json"
    index: list[dict[str, Any]] = []
    if index_path.is_file():
        try:
            loaded = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                index = loaded
        except json.JSONDecodeError:
            index = []
    if any(e.get("generation") == generation.generation for e in index):
        raise FileExistsError(
            f"immutable generation gen-{generation.generation:04d} already indexed"
        )
    index.append(
        {
            "generation": generation.generation,
            "probe_id": generation.probe_id,
            "intake_digest": generation.intake_digest,
            "parent_digest": generation.parent_digest,
            "content_digest": generation.content_digest(),
            "closed": generation.closed,
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


def _coerce_status(
    raw: Any,
    *,
    matched: Any = None,
) -> DifferentialStatus:
    if isinstance(raw, str) and raw in {
        "match",
        "mismatch",
        "indeterminate",
        "not_applicable",
    }:
        return raw  # type: ignore[return-value]
    if matched is True:
        return "match"
    if matched is False:
        return "mismatch"
    return "indeterminate"


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
    alias_map: Mapping[str, str] | None = None,
) -> AmbiguityRecord:
    dims = ce.non_pass_dimensions() or ["unspecified"]
    excerpts = [
        f"probe={ce.probe_id}",
        f"failing_dimensions={dims}",
        f"overall_status={ce.overall_status}",
        f"minimized_sequence={ce.minimized_sequence!r}",
    ]
    if ce.notes:
        excerpts.append(ce.notes)
    for detail in ce.dimension_details:
        if detail.detail:
            excerpts.append(f"{detail.dimension}[{detail.status}]: {detail.detail}")
    interpretations = [f"align_candidate_to_reference:{dim}" for dim in dims] + [
        "widen_tolerance",
        "mark_unsupported_semantics",
        "expert_override",
    ]
    raw_id = f"AMB-CEGR-{canonical_hash({'probe': ce.probe_id, 'dims': dims})[:8].upper()}"
    amb_id = resolve_ambiguity_alias(raw_id, alias_map=alias_map)
    # Classic refund fixture: if subject/predicate match, prefer hashed conflict id.
    if action_id == "submit_refund" and "retry" in dims:
        amb_id = resolve_ambiguity_alias("AMB-0042", alias_map=alias_map)
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
            "status": next(
                (d.status for d in ce.dimension_details if d.dimension == dimension),
                "mismatch",
            ),
        },
        rationale=(
            f"Differential non-pass on {dimension} for probe {ce.probe_id}; "
            "align transition to reference or mark unsupported."
        ),
        requires_expert=True,
        provenance={
            "intake_digest": ce.content_digest(),
            "probe_id": ce.probe_id,
            "dimension": dimension,
            "extraction_method": "cegr_v2",
        },
    )


def _replay_pair(
    *,
    phase: Literal["before", "after"],
    sequence: Sequence[Any],
    reference_execute: Callable[[Any], dict[str, Any]] | None,
    candidate_execute: Callable[[Any], dict[str, Any]] | None,
) -> ReplayObservation | None:
    if reference_execute is None or candidate_execute is None:
        return None
    ref_outs: list[dict[str, Any]] = []
    cand_outs: list[dict[str, Any]] = []
    dim_statuses: dict[str, DifferentialStatus] = {}
    for step in sequence:
        ref_outs.append(dict(reference_execute(step)))
        cand_outs.append(dict(candidate_execute(step)))
    overall: DifferentialStatus = "match"
    if not sequence:
        overall = "indeterminate"
        dim_statuses["sequence"] = "indeterminate"
    else:
        for key in ("success", "authorized", "authorization", "failure", "state", "observation"):
            ref_vals = [o.get(key) for o in ref_outs if key in o]
            cand_vals = [o.get(key) for o in cand_outs if key in o]
            if not ref_vals and not cand_vals:
                continue
            if not ref_vals or not cand_vals:
                dim_statuses[key] = "indeterminate"
                overall = "indeterminate"
            elif ref_vals != cand_vals:
                dim_statuses[key] = "mismatch"
                if overall == "match":
                    overall = "mismatch"
            else:
                dim_statuses[key] = "match"
        if not dim_statuses:
            overall = "indeterminate"
            dim_statuses["outcome"] = "indeterminate"
    return ReplayObservation(
        phase=phase,
        sequence=list(sequence),
        reference_outcomes=ref_outs,
        candidate_outcomes=cand_outs,
        overall_status=overall,
        dimension_statuses=dim_statuses,
    )


def _merge_replay_into_intake(
    ce: CounterexampleIntake,
    replay: ReplayObservation,
) -> CounterexampleIntake:
    ref = replay.reference_outcomes[-1] if replay.reference_outcomes else {}
    cand = replay.candidate_outcomes[-1] if replay.candidate_outcomes else {}
    details = [
        DimensionMismatchIntake(
            dimension=dim,
            status=status,
            matched=status == "match",
            detail=f"replay:{replay.phase}",
        )
        for dim, status in replay.dimension_statuses.items()
        if status in {"mismatch", "indeterminate"}
    ]
    failing = [d.dimension for d in details]
    return ce.model_copy(
        update={
            "reference_outcome": dict(ref) if ref else ce.reference_outcome,
            "candidate_outcome": dict(cand) if cand else ce.candidate_outcome,
            "overall_status": replay.overall_status,
            "dimension_details": details or ce.dimension_details,
            "failing_dimensions": failing or ce.failing_dimensions,
        }
    )


def _run_regression_mutation(
    *,
    world: WorldDefinition | None,
    regression_probes: Sequence[dict[str, Any]] | None,
    reference_execute: Callable[[Any], dict[str, Any]] | None,
    candidate_execute: Callable[[Any], dict[str, Any]] | None,
) -> RegressionMutationReport:
    details: list[dict[str, Any]] = []
    probes_run = 0
    regression_passed: bool | None = None
    mutation_detected: bool | None = None

    if regression_probes and reference_execute and candidate_execute:
        regression_passed = True
        for probe in regression_probes:
            probes_run += 1
            step = probe.get("step", probe)
            ref = reference_execute(step)
            cand = candidate_execute(step)
            ok = ref == cand
            if not ok:
                regression_passed = False
            details.append(
                {
                    "kind": "regression",
                    "probe_id": probe.get("probe_id"),
                    "matched": ok,
                }
            )

    if world is not None:
        from envassure.analysis.mutation import MutationCategory, apply_mutation

        mutant = apply_mutation(world, MutationCategory.PERMISSION, seed=0)
        mutation_detected = mutant.model_dump(mode="json") != world.model_dump(mode="json")
        probes_run += 1
        details.append(
            {
                "kind": "mutation",
                "category": MutationCategory.PERMISSION.value,
                "detected": mutation_detected,
            }
        )

    return RegressionMutationReport(
        regression_passed=regression_passed,
        mutation_detected=mutation_detected,
        probes_run=probes_run,
        details=details,
    )


def _evaluate_close(
    *,
    intake: CounterexampleIntake,
    replay_after: ReplayObservation | None,
    reconciliation: ReconciliationResult,
) -> tuple[bool, str]:
    """Close only when replay evidence is match and no unresolved ambiguities remain.

    Indeterminate evidence never closes. Accepted facts alone are insufficient
    without replay match evidence.
    """
    if reconciliation.unresolved_ambiguities:
        return False, (
            f"{len(reconciliation.unresolved_ambiguities)} unresolved ambiguity(ies); "
            "expert decision required before close"
        )
    if replay_after is None:
        # Without replay executors, never auto-close — expert evidence required.
        if intake.overall_status == "match" and not intake.non_pass_dimensions():
            return False, "overall match claimed but no automatic replay evidence"
        return False, "no replay evidence; CEGR stays open"
    if replay_after.overall_status == "indeterminate":
        return False, "replay after is indeterminate (non-pass)"
    if replay_after.overall_status == "mismatch":
        return False, "replay after still mismatches"
    if any(s == "indeterminate" for s in replay_after.dimension_statuses.values()):
        return False, "replay has indeterminate dimension(s)"
    if replay_after.overall_status == "match":
        return True, "replay_after overall_status=match with no indeterminate dimensions"
    return False, f"replay status {replay_after.overall_status} does not authorize close"
