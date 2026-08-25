"""Tests for the EAC-R15 local protocol-integrity boundary."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from envassure.benchmark.qualification import (
    EACR15EvidenceBundle,
    EACR15Registration,
    StochasticAnalysisRegistration,
    WorkflowEvidence,
    WorkflowRegistration,
    evaluate_eac_r15_bundle,
)

_ALL_ESTIMANDS = (
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
)


def _digest(char: str) -> str:
    return char * 64


def _workflow(family: str, index: int, *, probe_count: int = 100) -> WorkflowRegistration:
    stochastic = None
    if family == "stochastic_operational":
        stochastic = StochasticAnalysisRegistration(
            method="paired_mean_difference_ci",
            alpha=0.05,
            equivalence_margin=0.05,
            minimum_samples=100,
            assumptions=("paired probes are exchangeable within the declared operating regime",),
        )
    return WorkflowRegistration(
        family=family,  # type: ignore[arg-type]
        source_package_digest=_digest(str(index)),
        source_manifest_digest=_digest(chr(ord("a") + index)),
        reference_commitment=_digest(chr(ord("d") + index)),
        heldout_probe_commitment=_digest(chr(ord("g") + index)),
        heldout_probe_count=probe_count,
        estimands=_ALL_ESTIMANDS,
        stochastic_analysis=stochastic,
    )


def _registration() -> EACR15Registration:
    return EACR15Registration(
        study_id="eac-r15-test",
        envassure_commit="c7199ed26f8d94f9e288b51644de0b624bb1e97b",
        workflow_registrations=(
            _workflow("transactional_enterprise", 1),
            _workflow("authorization_heavy", 2),
            _workflow("stochastic_operational", 3),
        ),
        primary_estimands=_ALL_ESTIMANDS,
        multiple_comparison_policy="preregistered_primary",
        reference_custodian_commitment=_digest("a"),
        protocol_document_digest=_digest("b"),
    )


def _workflow_evidence(reg: WorkflowRegistration, index: int) -> WorkflowEvidence:
    return WorkflowEvidence(
        family=reg.family,
        source_package_digest=reg.source_package_digest,
        compiled_ir_digest=_digest(chr(ord("j") + index)),
        assumptions_digest=_digest(chr(ord("m") + index)),
        reconciliation_log_digest=_digest(chr(ord("p") + index)),
        heldout_probe_commitment=reg.heldout_probe_commitment,
        adjudicated_probe_count=reg.heldout_probe_count,
        raw_results_digest=_digest(chr(ord("s") + index)),
        statistics_digest=_digest(chr(ord("v") + index)),
        counterexamples_digest=_digest(chr(ord("0") + index)),
        expert_effort_digest=_digest(chr(ord("4") + index)),
        leakage_analysis_digest=_digest(chr(ord("7") + index)),
        status="complete",
    )


def _bundle(registration: EACR15Registration) -> EACR15EvidenceBundle:
    return EACR15EvidenceBundle(
        study_id=registration.study_id,
        registration_digest=registration.content_digest,
        envassure_commit=registration.envassure_commit,
        workflows=tuple(
            _workflow_evidence(item, index)
            for index, item in enumerate(registration.workflow_registrations)
        ),
        aggregate_report_digest=_digest("a"),
        negative_results_digest=_digest("b"),
        external_custodian_attestation_digest=_digest("c"),
        independent_reviewer_signoff_digest=_digest("d"),
    )


def test_registration_binds_exact_three_families_and_minimum_probe_count() -> None:
    registration = _registration()
    assert {item.family for item in registration.workflow_registrations} == {
        "transactional_enterprise",
        "authorization_heavy",
        "stochastic_operational",
    }
    assert all(item.heldout_probe_count >= 100 for item in registration.workflow_registrations)
    assert len(registration.content_digest) == 64

    with pytest.raises(ValidationError):
        _workflow("transactional_enterprise", 1, probe_count=99)


def test_registration_accepts_git_sha1_without_calling_it_sha256() -> None:
    registration = _registration()
    assert len(registration.envassure_commit) == 40

    payload = registration.model_dump(mode="json")
    payload["envassure_commit"] = "z" * 40
    with pytest.raises(ValidationError, match="Git object id"):
        EACR15Registration.model_validate(payload)


def test_stochastic_family_requires_preregistered_equivalence_method() -> None:
    with pytest.raises(ValidationError, match="stochastic_analysis"):
        WorkflowRegistration(
            family="stochastic_operational",
            source_package_digest=_digest("1"),
            source_manifest_digest=_digest("2"),
            reference_commitment=_digest("3"),
            heldout_probe_commitment=_digest("4"),
            heldout_probe_count=100,
            estimands=_ALL_ESTIMANDS,
        )


def test_public_generated_fixture_cannot_be_registered_as_qualification_reference() -> None:
    payload = _registration().model_dump(mode="json")
    payload["generated_fixture_suite_is_qualification_reference"] = True
    with pytest.raises(ValidationError):
        EACR15Registration.model_validate(payload)


def test_required_estimands_cannot_be_silently_omitted() -> None:
    payload = _registration().model_dump(mode="json")
    payload["primary_estimands"] = [
        value for value in payload["primary_estimands"] if value != "wrong_commitment_rate"
    ]
    with pytest.raises(ValidationError, match="wrong_commitment_rate"):
        EACR15Registration.model_validate(payload)


def test_locally_complete_bundle_is_still_not_a_qualification_claim() -> None:
    registration = _registration()
    evidence = _bundle(registration)
    assessment = evaluate_eac_r15_bundle(registration, evidence)

    assert assessment.local_protocol_integrity is True
    assert assessment.all_workflows_complete is True
    assert assessment.qualification_claim_permitted is False
    assert assessment.external_attestation_verification == "not_implemented"
    assert "external_custodian_attestation_unverified" in assessment.blockers
    assert "independent_reviewer_signoff_unverified" in assessment.blockers
    assert "external_concealment_verifier_not_implemented" in assessment.blockers


def test_probe_commitment_rebinding_breaks_local_integrity() -> None:
    registration = _registration()
    evidence = _bundle(registration)
    payload = evidence.model_dump(mode="json")
    payload["workflows"][0]["heldout_probe_commitment"] = _digest("f")
    rebound = EACR15EvidenceBundle.model_validate(payload)

    assessment = evaluate_eac_r15_bundle(registration, rebound)
    assert assessment.local_protocol_integrity is False
    assert assessment.all_workflows_complete is False
    assert "probe_commitment_mismatch:transactional_enterprise" in assessment.blockers


def test_underpowered_poststudy_evidence_is_not_complete() -> None:
    registration = _registration()
    evidence = _bundle(registration)
    payload = evidence.model_dump(mode="json")
    payload["workflows"][1]["adjudicated_probe_count"] = 99
    underpowered = EACR15EvidenceBundle.model_validate(payload)

    assessment = evaluate_eac_r15_bundle(registration, underpowered)
    assert assessment.local_protocol_integrity is False
    assert assessment.all_workflows_complete is False
    assert "insufficient_adjudicated_probes:authorization_heavy" in assessment.blockers


def test_indeterminate_workflow_requires_reason_and_propagates() -> None:
    registration = _registration()
    evidence = _bundle(registration)
    payload = evidence.model_dump(mode="json")
    payload["workflows"][2]["status"] = "indeterminate"
    payload["workflows"][2]["indeterminate_reasons"] = ["confidence interval overlaps margin"]
    indeterminate = EACR15EvidenceBundle.model_validate(payload)

    assessment = evaluate_eac_r15_bundle(registration, indeterminate)
    assert assessment.all_workflows_complete is False
    assert "workflow_not_complete:stochastic_operational:indeterminate" in assessment.blockers
