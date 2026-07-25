"""Verifier candidates, status hierarchy, and hidden-oracle leakage checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic, DiagnosticReport
from envassure.ir.models import VerifierClaim, WorldDefinition
from envassure.ir.primitives import VerifierStatus

MechanismName = Literal[
    "predicate",
    "execution",
    "temporal",
    "authority",
    "solver",
    "model_judged",
]

# Stronger mechanisms appear later; model_judged is weakest for authority claims.
MECHANISM_HIERARCHY: tuple[MechanismName, ...] = (
    "model_judged",
    "solver",
    "authority",
    "temporal",
    "execution",
    "predicate",
)

# Promotion order for release evidence (candidate is entry; deprecated is terminal).
STATUS_HIERARCHY: tuple[VerifierStatus, ...] = (
    "candidate",
    "draft",
    "tested",
    "differentially_validated",
    "qualified_external",
    "deprecated",
)

_STATUS_RANK = {status: idx for idx, status in enumerate(STATUS_HIERARCHY)}
_MECHANISM_RANK = {name: idx for idx, name in enumerate(MECHANISM_HIERARCHY)}


@dataclass(slots=True)
class VerifierCandidate:
    """
    Working candidate wrapping a VerifierClaim with hierarchy helpers.

    Status promotions are explicit; never auto-accepted from model proposals.
    """

    claim: VerifierClaim
    policy_only: bool = True
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> VerifierStatus:
        return self.claim.status

    @property
    def mechanism(self) -> str:
        return self.claim.mechanism

    def status_rank(self) -> int:
        return _STATUS_RANK.get(self.claim.status, 0)

    def mechanism_rank(self) -> int:
        return _MECHANISM_RANK.get(self.claim.mechanism, 0)  # type: ignore[arg-type]

    def can_promote_to(self, target: VerifierStatus) -> bool:
        if target == "deprecated":
            return self.claim.status != "deprecated"
        return _STATUS_RANK.get(target, -1) > self.status_rank()

    def promote(self, target: VerifierStatus, *, reason: str) -> None:
        if not self.can_promote_to(target):
            raise ValueError(
                f"cannot promote verifier {self.claim.id} from {self.claim.status} to {target}"
            )
        self.claim.status = target
        self.notes.append(f"promoted to {target}: {reason}")

    def as_claim(self) -> VerifierClaim:
        return self.claim.model_copy(deep=True)


def from_claim(claim: VerifierClaim, *, policy_only: bool = True) -> VerifierCandidate:
    return VerifierCandidate(claim=claim.model_copy(deep=True), policy_only=policy_only)


def compare_status(a: VerifierStatus, b: VerifierStatus) -> int:
    """Return negative if a < b in hierarchy, zero if equal, positive if a > b."""
    return _STATUS_RANK.get(a, 0) - _STATUS_RANK.get(b, 0)


def check_hidden_oracle_leakage(
    world: WorldDefinition,
    verifier: VerifierClaim | VerifierCandidate,
    *,
    policy_only: bool | None = None,
) -> list[Diagnostic]:
    """
    Flag verifiers that claim policy-only evidence but reference evaluator_visible state.

    Heuristic: scan decision_rule, statement, and required_evidence for state ids
    marked evaluator_visible with policy_visible=False.
    """
    claim = verifier.claim if isinstance(verifier, VerifierCandidate) else verifier
    assumes_policy_only = policy_only
    if assumes_policy_only is None:
        if isinstance(verifier, VerifierCandidate):
            assumes_policy_only = verifier.policy_only
        else:
            assumes_policy_only = "policy" in " ".join(claim.assumptions).lower() or True

    if not assumes_policy_only:
        return []

    hidden = [s for s in world.state if s.evaluator_visible and not s.policy_visible]
    if not hidden:
        return []

    corpus = " ".join(
        [
            claim.decision_rule,
            claim.statement,
            *claim.required_evidence,
            *claim.assumptions,
        ]
    )
    diagnostics: list[Diagnostic] = []
    for var in hidden:
        if var.id in corpus or f"state.{var.id}" in corpus:
            diagnostics.append(
                make_diagnostic(
                    "EAC6002",
                    verifier_id=claim.id,
                    reason=(
                        f"references evaluator_visible state {var.id!r} while "
                        "claiming policy-only evidence"
                    ),
                    subject=claim.id,
                    details={"state_id": var.id},
                    affected_artifacts=[f"verifier:{claim.id}", f"state:{var.id}"],
                )
            )
    return diagnostics


def audit_verifiers(world: WorldDefinition) -> DiagnosticReport:
    """Run hidden-oracle leakage checks across all verifiers in *world*."""
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    for claim in world.verifiers:
        report.extend(check_hidden_oracle_leakage(world, claim))
    return report
