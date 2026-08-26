"""Qualification-protocol artifacts for the real EAC-R15 hidden-reference study.

The public repository can enforce *local protocol integrity*: preregistration,
content commitments, required workflow families, minimum probe counts, typed
estimands, and result-to-registration binding. It cannot prove that a reference
system was actually concealed from the compiler team or that a reviewer was
independent merely because a local file says so.

Accordingly, :func:`evaluate_eac_r15_bundle` never emits a scientific or
independent qualification verdict. External concealment/custodian/reviewer
attestations require a separately trusted verifier that is intentionally not
implemented here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from envassure.canonical import canonical_hash

EAC_R15_SCHEMA_VERSION = "1"
MIN_HELDOUT_PROBES_PER_FAMILY = 100

WorkflowFamily = Literal[
    "transactional_enterprise",
    "authorization_heavy",
    "stochastic_operational",
]

EstimandName = Literal[
    "fact_precision_by_evidence_class",
    "fact_recall_by_evidence_class",
    "wrong_commitment_rate",
    "correct_abstention_rate",
    "incorrect_abstention_rate",
    "source_conflict_rate",
    "transition_agreement",
    "authorization_agreement",
    "failure_agreement",
    "observation_agreement",
    "stochastic_equivalence",
    "hidden_reference_leakage",
    "cegr_counterexample_rate",
    "expert_correction_time",
    "expert_decision_count",
    "unseen_behavior_rate",
]

_REQUIRED_FAMILIES: frozenset[str] = frozenset(
    {"transactional_enterprise", "authorization_heavy", "stochastic_operational"}
)
_REQUIRED_ESTIMANDS: frozenset[str] = frozenset(
    {
        "fact_precision_by_evidence_class",
        "fact_recall_by_evidence_class",
        "wrong_commitment_rate",
        "correct_abstention_rate",
        "incorrect_abstention_rate",
        "source_conflict_rate",
        "transition_agreement",
        "authorization_agreement",
        "failure_agreement",
        "observation_agreement",
        "stochastic_equivalence",
        "hidden_reference_leakage",
        "cegr_counterexample_rate",
        "expert_correction_time",
        "expert_decision_count",
        "unseen_behavior_rate",
    }
)


def _sha256(value: str, *, field: str) -> str:
    text = value.strip().lower()
    if len(text) != 64 or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be a lowercase sha256 digest")
    return text


def _git_object_id(value: str, *, field: str) -> str:
    """Validate a Git object ID without conflating it with artifact SHA-256."""
    text = value.strip().lower()
    if len(text) not in {40, 64} or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{field} must be a 40- or 64-hex Git object id")
    return text


class StochasticAnalysisRegistration(BaseModel):
    """Exact preregistration binding for the stochastic-family analysis."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method_id: str = Field(min_length=1)
    method_document_digest: str
    alpha: float = Field(gt=0.0, lt=1.0)
    equivalence_margin: float = Field(gt=0.0, lt=1.0)
    minimum_samples: int = Field(ge=MIN_HELDOUT_PROBES_PER_FAMILY)
    assumptions: tuple[str, ...] = Field(min_length=1)

    @field_validator("method_id")
    @classmethod
    def _method_identifier(cls, value: str) -> str:
        identifier = value.strip()
        if not identifier:
            raise ValueError("method_id must be non-empty after trimming")
        return identifier

    @field_validator("method_document_digest")
    @classmethod
    def _method_digest(cls, value: str, info: Any) -> str:
        return _sha256(value, field=info.field_name)

    @field_validator("assumptions")
    @classmethod
    def _assumptions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value)
        if any(not item for item in cleaned):
            raise ValueError("assumptions must contain only non-empty strings")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("assumptions must not contain duplicates")
        return cleaned


class WorkflowRegistration(BaseModel):
    """One independently referenced workflow family in the qualification study."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family: WorkflowFamily
    source_package_digest: str
    source_manifest_digest: str
    reference_commitment: str
    heldout_probe_commitment: str
    heldout_probe_count: int = Field(ge=MIN_HELDOUT_PROBES_PER_FAMILY)
    estimands: tuple[EstimandName, ...] = Field(min_length=1)
    stochastic_analysis: StochasticAnalysisRegistration | None = None

    @field_validator(
        "source_package_digest",
        "source_manifest_digest",
        "reference_commitment",
        "heldout_probe_commitment",
    )
    @classmethod
    def _digest(cls, value: str, info: Any) -> str:
        return _sha256(value, field=info.field_name)

    @model_validator(mode="after")
    def _stochastic_plan_matches_family(self) -> WorkflowRegistration:
        if self.family == "stochastic_operational" and self.stochastic_analysis is None:
            raise ValueError("stochastic_operational requires a preregistered stochastic_analysis")
        if self.family != "stochastic_operational" and self.stochastic_analysis is not None:
            raise ValueError("stochastic_analysis is only valid for stochastic_operational")
        if (
            self.stochastic_analysis is not None
            and self.stochastic_analysis.minimum_samples > self.heldout_probe_count
        ):
            raise ValueError(
                "stochastic minimum_samples cannot exceed the committed heldout_probe_count"
            )
        return self


class EACR15Registration(BaseModel):
    """Immutable pre-compilation commitment for the EAC-R15 experiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    study_id: str = Field(min_length=1)
    protocol: Literal["EAC-R15"] = "EAC-R15"
    envassure_commit: str
    workflow_registrations: tuple[WorkflowRegistration, ...] = Field(min_length=3, max_length=3)
    primary_estimands: tuple[EstimandName, ...] = Field(min_length=1)
    multiple_comparison_policy: Literal["none", "bonferroni", "holm", "preregistered_primary"]
    reference_custodian_commitment: str
    protocol_document_digest: str
    prohibited_reference_access_before_freeze: bool = True
    generated_fixture_suite_is_qualification_reference: Literal[False] = False
    metadata_digest: str | None = None

    @field_validator("envassure_commit")
    @classmethod
    def _commit_id(cls, value: str, info: Any) -> str:
        return _git_object_id(value, field=info.field_name)

    @field_validator("reference_custodian_commitment", "protocol_document_digest")
    @classmethod
    def _root_digest(cls, value: str, info: Any) -> str:
        return _sha256(value, field=info.field_name)

    @field_validator("metadata_digest")
    @classmethod
    def _optional_registration_digest(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _sha256(value, field=info.field_name)

    @model_validator(mode="after")
    def _required_scope(self) -> EACR15Registration:
        families = [item.family for item in self.workflow_registrations]
        if len(set(families)) != len(families):
            raise ValueError("workflow families must be unique")
        if frozenset(families) != _REQUIRED_FAMILIES:
            raise ValueError(
                "EAC-R15 requires exactly transactional_enterprise, authorization_heavy, "
                "and stochastic_operational workflow families"
            )
        estimands = set(self.primary_estimands)
        if not _REQUIRED_ESTIMANDS.issubset(estimands):
            missing = sorted(_REQUIRED_ESTIMANDS - estimands)
            raise ValueError(f"EAC-R15 primary estimands missing required entries: {missing}")
        if not self.prohibited_reference_access_before_freeze:
            raise ValueError(
                "qualification registration must prohibit reference access before freeze"
            )
        return self

    @property
    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class WorkflowEvidence(BaseModel):
    """Locally verifiable result bindings for one registered workflow."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    family: WorkflowFamily
    source_package_digest: str
    source_manifest_digest: str
    reference_commitment: str
    compiled_ir_digest: str
    assumptions_digest: str
    reconciliation_log_digest: str
    heldout_probe_commitment: str
    analysis_method_document_digest: str | None = None
    adjudicated_probe_count: int = Field(ge=0)
    raw_results_digest: str
    statistics_digest: str
    counterexamples_digest: str
    expert_effort_digest: str
    leakage_analysis_digest: str
    status: Literal["complete", "indeterminate", "invalid"]
    indeterminate_reasons: tuple[str, ...] = ()

    @field_validator(
        "source_package_digest",
        "source_manifest_digest",
        "reference_commitment",
        "compiled_ir_digest",
        "assumptions_digest",
        "reconciliation_log_digest",
        "heldout_probe_commitment",
        "raw_results_digest",
        "statistics_digest",
        "counterexamples_digest",
        "expert_effort_digest",
        "leakage_analysis_digest",
    )
    @classmethod
    def _evidence_digest(cls, value: str, info: Any) -> str:
        return _sha256(value, field=info.field_name)

    @field_validator("analysis_method_document_digest")
    @classmethod
    def _optional_analysis_method_digest(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _sha256(value, field=info.field_name)

    @model_validator(mode="after")
    def _status_consistency(self) -> WorkflowEvidence:
        reasons = tuple(reason.strip() for reason in self.indeterminate_reasons)
        if any(not reason for reason in reasons):
            raise ValueError("evidence reasons must be non-empty strings")
        if len(set(reasons)) != len(reasons):
            raise ValueError("evidence reasons must not contain duplicates")
        if self.status == "complete" and reasons:
            raise ValueError("complete evidence cannot carry indeterminate reasons")
        if self.status in {"indeterminate", "invalid"} and not reasons:
            raise ValueError(f"{self.status} evidence requires at least one reason")
        if self.family == "stochastic_operational" and self.analysis_method_document_digest is None:
            raise ValueError(
                "stochastic_operational evidence requires analysis_method_document_digest"
            )
        if (
            self.family != "stochastic_operational"
            and self.analysis_method_document_digest is not None
        ):
            raise ValueError(
                "analysis_method_document_digest is only valid for stochastic_operational"
            )
        object.__setattr__(self, "indeterminate_reasons", reasons)
        return self


class EACR15EvidenceBundle(BaseModel):
    """Post-study local evidence bundle bound to one preregistration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    study_id: str = Field(min_length=1)
    registration_digest: str
    envassure_commit: str
    workflows: tuple[WorkflowEvidence, ...] = Field(min_length=3, max_length=3)
    aggregate_report_digest: str
    negative_results_digest: str
    external_custodian_attestation_digest: str | None = None
    independent_reviewer_signoff_digest: str | None = None
    metadata_digest: str | None = None

    @field_validator("registration_digest", "aggregate_report_digest", "negative_results_digest")
    @classmethod
    def _bundle_digest(cls, value: str, info: Any) -> str:
        return _sha256(value, field=info.field_name)

    @field_validator("envassure_commit")
    @classmethod
    def _bundle_commit_id(cls, value: str, info: Any) -> str:
        return _git_object_id(value, field=info.field_name)

    @field_validator(
        "external_custodian_attestation_digest",
        "independent_reviewer_signoff_digest",
        "metadata_digest",
    )
    @classmethod
    def _optional_bundle_digest(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _sha256(value, field=info.field_name)

    @property
    def content_digest(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


class EACR15ProtocolAssessment(BaseModel):
    """Local integrity assessment; deliberately not a qualification verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    study_id: str
    registration_digest: str
    evidence_bundle_digest: str
    local_protocol_integrity: bool
    all_workflows_complete: bool
    qualification_claim_permitted: Literal[False] = False
    external_attestation_verification: Literal["not_implemented"] = "not_implemented"
    blockers: tuple[str, ...]
    notes: tuple[str, ...]


def evaluate_eac_r15_bundle(
    registration: EACR15Registration,
    evidence: EACR15EvidenceBundle,
) -> EACR15ProtocolAssessment:
    """Check only facts the repository can establish from local artifacts.

    Even a locally perfect bundle remains non-qualifying because this function
    has no independently trusted mechanism for verifying concealment, custodian
    independence, or reviewer independence.
    """
    blockers: list[str] = []
    if evidence.study_id != registration.study_id:
        blockers.append("study_id_mismatch")
    if evidence.registration_digest != registration.content_digest:
        blockers.append("registration_digest_mismatch")
    if evidence.envassure_commit != registration.envassure_commit:
        blockers.append("envassure_commit_mismatch")

    registered = {item.family: item for item in registration.workflow_registrations}
    observed: dict[str, WorkflowEvidence] = {}
    for item in evidence.workflows:
        if item.family in observed:
            blockers.append(f"duplicate_workflow_evidence:{item.family}")
        observed[item.family] = item

    if set(observed) != set(registered):
        blockers.append("workflow_family_set_mismatch")

    all_complete = True
    for family, expected in registered.items():
        evidence_item = observed.get(family)
        if evidence_item is None:
            all_complete = False
            continue
        if evidence_item.source_package_digest != expected.source_package_digest:
            blockers.append(f"source_package_digest_mismatch:{family}")
        if evidence_item.source_manifest_digest != expected.source_manifest_digest:
            blockers.append(f"source_manifest_digest_mismatch:{family}")
        if evidence_item.reference_commitment != expected.reference_commitment:
            blockers.append(f"reference_commitment_mismatch:{family}")
        if evidence_item.heldout_probe_commitment != expected.heldout_probe_commitment:
            blockers.append(f"probe_commitment_mismatch:{family}")
        if evidence_item.adjudicated_probe_count < expected.heldout_probe_count:
            blockers.append(f"insufficient_adjudicated_probes:{family}")
        if evidence_item.adjudicated_probe_count > expected.heldout_probe_count:
            blockers.append(f"uncommitted_adjudicated_probes:{family}")
        expected_method_digest = (
            expected.stochastic_analysis.method_document_digest
            if expected.stochastic_analysis is not None
            else None
        )
        if evidence_item.analysis_method_document_digest != expected_method_digest:
            blockers.append(f"analysis_method_digest_mismatch:{family}")
        if evidence_item.status != "complete":
            all_complete = False
            blockers.append(f"workflow_not_complete:{family}:{evidence_item.status}")

    # Presence is recorded, but local presence is not trusted attestation verification.
    if evidence.external_custodian_attestation_digest is None:
        blockers.append("external_custodian_attestation_absent")
    else:
        blockers.append("external_custodian_attestation_unverified")
    if evidence.independent_reviewer_signoff_digest is None:
        blockers.append("independent_reviewer_signoff_absent")
    else:
        blockers.append("independent_reviewer_signoff_unverified")
    blockers.append("external_concealment_verifier_not_implemented")

    local_integrity_blockers = [
        blocker
        for blocker in blockers
        if not blocker.startswith("external_custodian_")
        and not blocker.startswith("independent_reviewer_")
        and blocker != "external_concealment_verifier_not_implemented"
    ]
    local_integrity = not local_integrity_blockers
    notes = (
        "Local protocol integrity is not evidence that the reference was concealed.",
        "The public generated regression suite cannot satisfy EAC-R15 concealment.",
        "Independent custodian/reviewer attestations require a separately trusted verifier.",
        "Missing, uncommitted, or underpowered workflow evidence remains indeterminate; no scalar fidelity average is emitted.",
    )
    return EACR15ProtocolAssessment(
        study_id=registration.study_id,
        registration_digest=registration.content_digest,
        evidence_bundle_digest=evidence.content_digest,
        local_protocol_integrity=local_integrity,
        all_workflows_complete=all_complete and local_integrity,
        blockers=tuple(sorted(set(blockers))),
        notes=notes,
    )


__all__ = [
    "MIN_HELDOUT_PROBES_PER_FAMILY",
    "EACR15EvidenceBundle",
    "EACR15ProtocolAssessment",
    "EACR15Registration",
    "EstimandName",
    "StochasticAnalysisRegistration",
    "WorkflowEvidence",
    "WorkflowFamily",
    "WorkflowRegistration",
    "evaluate_eac_r15_bundle",
]
