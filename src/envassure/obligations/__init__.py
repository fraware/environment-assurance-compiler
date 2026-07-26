"""EvidenceObligation helpers and proof-obligation compiler (EAC-R14)."""

from __future__ import annotations

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import EvidenceObligation, WorldDefinition
from envassure.ir.primitives import ProvenanceRef
from envassure.obligations.generators import (
    compile_proof_obligations,
    generate_authorization_preservation,
    generate_deterministic_reset_replay,
    generate_idempotency_safety,
    generate_observation_separation,
    generate_resource_conservation,
    generate_reward_trace_binding,
    proof_obligation_pack_members,
    validate_proof_obligations,
)
from envassure.obligations.ir import (
    ClaimKind,
    MechanismStrength,
    ObligationStatus,
    ProofObligation,
    ProofObligationBundle,
)

__all__ = [
    "ClaimKind",
    "MechanismStrength",
    "ObligationStatus",
    "ProofObligation",
    "ProofObligationBundle",
    "compile_proof_obligations",
    "ensure_action_evidence",
    "generate_authorization_preservation",
    "generate_deterministic_reset_replay",
    "generate_idempotency_safety",
    "generate_observation_separation",
    "generate_resource_conservation",
    "generate_reward_trace_binding",
    "make_obligation",
    "obligations_for_action",
    "proof_obligation_pack_members",
    "validate_obligations",
    "validate_proof_obligations",
]


def make_obligation(
    obligation_id: str,
    *,
    trigger: str,
    evidence_class: str,
    producer: str,
    consumer: str,
    **kwargs: object,
) -> EvidenceObligation:
    """Construct an EvidenceObligation with safe defaults."""
    provenance = kwargs.pop("provenance", None)
    if provenance is None:
        provenance = ProvenanceRef()
    return EvidenceObligation(
        id=obligation_id,
        trigger=trigger,
        evidence_class=evidence_class,
        producer=producer,
        consumer=consumer,
        provenance=provenance,  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def obligations_for_action(
    world: WorldDefinition,
    action_id: str,
) -> list[EvidenceObligation]:
    """Return obligations whose trigger mentions *action_id* or producer is the action."""
    matched: list[EvidenceObligation] = []
    for obl in world.evidence_obligations:
        if action_id in obl.trigger or obl.producer == action_id:
            matched.append(obl)
    return matched


def ensure_action_evidence(
    world: WorldDefinition,
    action_id: str,
    *,
    evidence_class: str = "action_receipt",
    consumer: str = "verifier",
) -> EvidenceObligation:
    """
    Ensure an evidence obligation exists for *action_id*; append if missing.

    Mutates *world* in place and returns the obligation.
    """
    existing = obligations_for_action(world, action_id)
    if existing:
        return existing[0]
    obl = make_obligation(
        f"obl.{action_id}",
        trigger=f"on_action:{action_id}",
        evidence_class=evidence_class,
        producer=action_id,
        consumer=consumer,
    )
    world.evidence_obligations.append(obl)
    # Mirror onto action evidence_emitted when present.
    for action in world.actions:
        if action.id == action_id and obl.id not in action.evidence_emitted:
            action.evidence_emitted.append(obl.id)
    return obl


def validate_obligations(world: WorldDefinition) -> DiagnosticReport:
    """Check obligation producers/consumers reference known IR elements."""
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    action_ids = {a.id for a in world.actions}
    verifier_ids = {v.id for v in world.verifiers}
    known_consumers = verifier_ids | {"verifier", "evaluator", "pack", "audit"}
    seen: set[str] = set()
    for obl in world.evidence_obligations:
        if obl.id in seen:
            report.add(
                make_diagnostic(
                    "EAC3003",
                    reason=f"duplicate evidence obligation id {obl.id!r}",
                    subject=obl.id,
                )
            )
        seen.add(obl.id)
        if obl.producer not in action_ids and not obl.producer.startswith("system:"):
            report.add(
                make_diagnostic(
                    "EAC3002",
                    reason=(
                        f"obligation {obl.id!r} producer {obl.producer!r} is not a known action"
                    ),
                    subject=obl.id,
                )
            )
        if obl.consumer not in known_consumers and obl.consumer not in action_ids:
            report.add(
                make_diagnostic(
                    "EAC6001",
                    reason=(
                        f"obligation {obl.id!r} consumer {obl.consumer!r} "
                        "is not a known verifier or reserved consumer"
                    ),
                    subject=obl.id,
                )
            )
    # Also compile and validate proof-obligation bundle (non-blocking notes via same report).
    bundle = compile_proof_obligations(world)
    report.extend(validate_proof_obligations(bundle, world=world).diagnostics)
    return report
