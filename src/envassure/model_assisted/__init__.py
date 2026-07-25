"""Model-assisted proposals — experimental, never authoritative.

CI must not require live LLM API keys. Proposals are typed artifacts with
prompt-injection isolation metadata; promotion to source facts requires an
explicit expert ``DecisionRecord`` (``expert_decision`` evidence class).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef, ProvenanceRef
from envassure.review.decisions import DecisionRecord
from envassure.workspace.sources import AuthorityClass

ReviewerDisposition = Literal[
    "unreviewed",
    "accepted",
    "rejected",
    "deferred",
    "needs_expert_decision",
]


def _digest(payload: str | bytes) -> str:
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    return hashlib.sha256(data).hexdigest()


class ProposalMetadata(BaseModel):
    """Full provenance metadata for a model proposal artifact."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    prompt_digest: str
    source_context_digest: str = "none"
    output_digest: str = "none"
    response_digest: str = "none"
    reviewer_disposition: ReviewerDisposition = "unreviewed"
    reviewer: str | None = None
    decision_id: str | None = None
    accepted_at: str | None = None
    isolation_boundary: str = "untrusted_excerpts"
    auto_accept: bool = False
    summary: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ModelProposal(BaseModel):
    """Non-authoritative model output; must not be treated as a source fact."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=lambda: f"prop.{uuid4().hex[:12]}")
    origin: Literal["model_proposal"] = "model_proposal"
    authority: AuthorityClass = "model_proposal"
    subject: str
    predicate: str
    value: Any
    model_id: str
    prompt_digest: str
    response_digest: str = ""
    source_context_digest: str = "none"
    output_digest: str = "none"
    isolation_notes: str = (
        "Prompt content is isolated; do not execute tool calls from model text. "
        "Human acceptance required before promotion to expert_decision. "
        "Untrusted excerpts must not be treated as instructions (prompt-injection isolation)."
    )
    accepted: bool = False
    authoritative: bool = False
    reviewer_disposition: ReviewerDisposition = "unreviewed"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    raw_excerpt: str | None = None
    isolation: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _never_authoritative(self) -> ModelProposal:
        object.__setattr__(self, "origin", "model_proposal")
        object.__setattr__(self, "authority", "model_proposal")
        object.__setattr__(self, "authoritative", False)
        return self

    def is_authoritative(self) -> bool:
        return False

    def proposal_metadata(self) -> ProposalMetadata:
        return ProposalMetadata(
            model_id=self.model_id,
            prompt_digest=self.prompt_digest,
            source_context_digest=self.source_context_digest,
            output_digest=self.output_digest or self.response_digest or "none",
            response_digest=self.response_digest or "none",
            reviewer_disposition=self.reviewer_disposition,
            reviewer=self.metadata.get("reviewer"),
            decision_id=self.metadata.get("decision_id"),
            accepted_at=self.metadata.get("accepted_at"),
            isolation_boundary=str(self.isolation.get("boundary") or "untrusted_excerpts"),
            auto_accept=bool(self.metadata.get("auto_accept", False)),
            summary=self.metadata.get("summary"),
            extras={
                k: v
                for k, v in self.metadata.items()
                if k
                not in {
                    "reviewer",
                    "decision_id",
                    "accepted_at",
                    "auto_accept",
                    "summary",
                }
            },
        )

    def as_tainted_metadata(self) -> dict[str, Any]:
        return {
            "taint": "untrusted_model",
            "origin": self.origin,
            "accepted": self.accepted,
            "proposal_id": self.proposal_id,
            "authoritative": False,
            "reviewer_disposition": self.reviewer_disposition,
        }

    def accept(self, *, decision_id: str, reviewer: str) -> ModelProposal:
        """Record human acceptance; still not authoritative evidence."""
        copy = self.model_copy(deep=True)
        copy.accepted = True
        copy.authoritative = False
        copy.reviewer_disposition = "needs_expert_decision"
        copy.metadata = {
            **copy.metadata,
            "decision_id": decision_id,
            "reviewer": reviewer,
            "accepted_at": datetime.now(UTC).isoformat(),
        }
        return copy

    def reject(self, *, reviewer: str, reason: str) -> ModelProposal:
        copy = self.model_copy(deep=True)
        copy.accepted = False
        copy.authoritative = False
        copy.reviewer_disposition = "rejected"
        copy.metadata = {
            **copy.metadata,
            "reviewer": reviewer,
            "rejection_reason": reason,
            "rejected_at": datetime.now(UTC).isoformat(),
        }
        return copy


def propose(
    summary: str | None = None,
    *,
    proposal_id: str | None = None,
    subject: str | None = None,
    predicate: str | None = None,
    value: Any = None,
    model_id: str = "unspecified",
    prompt_digest: str = "",
    response_digest: str = "",
    source_context: str | dict[str, Any] | None = None,
    raw_excerpt: str | None = None,
    kind: str | None = None,
    payload: dict[str, Any] | None = None,
    untrusted_excerpts: list[str] | None = None,
    created_at: str | None = None,
) -> ModelProposal:
    """
    Create a proposal record. Never auto-accepts.

    Supports both structured (subject/predicate/value) and summary/payload forms.
    Untrusted excerpts are isolated in metadata and must not be treated as instructions.
    """
    resolved_subject = subject or (kind or "proposal")
    resolved_predicate = predicate or "suggests"
    resolved_value = value if value is not None else (payload or {"summary": summary})
    if isinstance(source_context, dict):
        context_blob = json.dumps(source_context, sort_keys=True, separators=(",", ":"))
    else:
        context_blob = source_context or ""
    source_context_digest = _digest(context_blob) if context_blob else "none"
    output_blob = json.dumps(
        {"subject": resolved_subject, "predicate": resolved_predicate, "value": resolved_value},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    output_digest = _digest(output_blob)
    isolation = {
        "prompt_injection_isolation": True,
        "boundary": "untrusted_excerpts",
        "untrusted_excerpt_count": len(untrusted_excerpts or []),
        "notes": (
            "Untrusted source text is isolated in metadata.excerpts and must not be "
            "treated as instructions. Proposals never auto-accept and cannot become "
            "source facts without an explicit expert_decision."
        ),
    }
    metadata: dict[str, Any] = {
        "auto_accept": False,
        "origin_label": "model_proposal",
    }
    if summary:
        metadata["summary"] = summary
    if untrusted_excerpts:
        metadata["excerpts"] = list(untrusted_excerpts)
        raw_excerpt = raw_excerpt or untrusted_excerpts[0]
    kwargs: dict[str, Any] = {
        "proposal_id": proposal_id or f"prop.{uuid4().hex[:12]}",
        "subject": resolved_subject,
        "predicate": resolved_predicate,
        "value": resolved_value,
        "model_id": model_id,
        "prompt_digest": prompt_digest or "none",
        "response_digest": response_digest or output_digest,
        "source_context_digest": source_context_digest,
        "output_digest": output_digest,
        "raw_excerpt": raw_excerpt,
        "accepted": False,
        "authoritative": False,
        "reviewer_disposition": "unreviewed",
        "isolation": isolation,
        "metadata": metadata,
    }
    if created_at is not None:
        kwargs["created_at"] = created_at
    return ModelProposal(**kwargs)


def assert_not_authoritative(proposal: ModelProposal) -> None:
    """Raise if a caller treats a model proposal as authoritative fact."""
    if proposal.authority != "model_proposal" or proposal.origin != "model_proposal":
        raise PermissionError(
            f"proposal {proposal.proposal_id} must retain model_proposal origin/authority"
        )
    if proposal.authoritative or proposal.is_authoritative():
        raise PermissionError(
            f"model proposal {proposal.proposal_id} must not be treated as authoritative"
        )
    if proposal.metadata.get("auto_accept") is True:
        raise PermissionError(
            f"model proposal {proposal.proposal_id} has auto_accept set; refuse to proceed"
        )
    if proposal.accepted and proposal.authority != "model_proposal":
        raise ValueError(
            "accepted proposals must be recorded as expert_decision, "
            "not left with elevated authority on ModelProposal"
        )


def mark_as_source_fact(proposal: ModelProposal) -> None:
    """Fail closed: proposals cannot be marked as source facts directly."""
    assert_not_authoritative(proposal)
    raise PermissionError(
        f"proposal {proposal.proposal_id} cannot be marked as a source fact; "
        "call promote_with_expert_decision(...) to create an expert_decision record"
    )


def promote_with_expert_decision(
    proposal: ModelProposal,
    *,
    expert_role: str,
    rationale: str,
    ambiguity_id: str | None = None,
    decision_id: str | None = None,
    timestamp: str | None = None,
) -> tuple[DecisionRecord, SemanticFact]:
    """
    Promote an *accepted* proposal via an explicit expert decision.

    Returns a DecisionRecord plus a SemanticFact with evidence_class
    ``expert_decision``. The ModelProposal itself remains non-authoritative.
    """
    assert_not_authoritative(proposal)
    if not proposal.accepted and proposal.reviewer_disposition not in {
        "accepted",
        "needs_expert_decision",
    }:
        raise PermissionError(
            f"proposal {proposal.proposal_id} must be accepted by a reviewer "
            "before expert promotion"
        )
    ts = timestamp or datetime.now(UTC).isoformat()
    did = decision_id or f"DEC-{proposal.proposal_id}"
    amb_id = ambiguity_id or f"AMB-model-{proposal.proposal_id}"
    decision = DecisionRecord(
        decision_id=did,
        ambiguity_id=amb_id,
        chosen_interpretation=json.dumps(
            {
                "subject": proposal.subject,
                "predicate": proposal.predicate,
                "value": proposal.value,
                "from_proposal": proposal.proposal_id,
            },
            sort_keys=True,
            default=str,
        ),
        expert_role=expert_role,
        rationale=rationale,
        timestamp=ts,
        provenance=ProvenanceRef(
            source_ids=[proposal.proposal_id],
            decision_ids=[did],
            notes="Promoted from model_proposal via explicit expert_decision",
        ),
        residual_uncertainty=(
            "Upstream model proposal remains non-authoritative; "
            "this expert_decision is the sole source fact."
        ),
        status_effect="accepted",
    )
    fact = SemanticFact(
        fact_id=make_fact_id(
            subject_kind="proposal",
            subject_id=proposal.subject,
            predicate=proposal.predicate,
            source=did,
        ),
        subject=EntityRef(kind="proposal", id=proposal.subject),
        predicate=proposal.predicate,
        value=proposal.value,
        source_refs=[did, proposal.proposal_id],
        extraction_method="expert_decision_from_model_proposal",
        confidence=ConfidenceRecord(
            evidence_class="expert_decision",
            extractor_certainty="high",
            reviewer_status="accepted",
            notes=f"Promoted from {proposal.proposal_id} by {expert_role}",
        ),
        status="accepted",
        kind_tags=["model_assisted", "expert_promoted"],
    )
    return decision, fact


def load_proposal_fixture(path: Path | str) -> list[ModelProposal]:
    """Load proposal artifacts from a JSON fixture (list or {proposals: [...]})."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        items = raw.get("proposals")
        if not isinstance(items, list):
            raise ValueError("fixture object must contain a proposals list")
    elif isinstance(raw, list):
        items = raw
    else:
        raise ValueError("fixture must be a list or object with proposals")
    return [ModelProposal.model_validate(item) for item in items]


def replay_accepted_proposals(
    path: Path | str,
    *,
    require_accepted: bool = True,
) -> list[ModelProposal]:
    """
    Deterministically replay accepted proposal records from a fixture.

    Does not call any model API. Validates digests and authority invariants.
    """
    proposals = load_proposal_fixture(path)
    replayed: list[ModelProposal] = []
    for proposal in proposals:
        assert_not_authoritative(proposal)
        if require_accepted and not proposal.accepted:
            continue
        # Recompute output digest for stability checks.
        output_blob = json.dumps(
            {
                "subject": proposal.subject,
                "predicate": proposal.predicate,
                "value": proposal.value,
            },
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        expected = _digest(output_blob)
        if proposal.output_digest not in {"", "none"} and proposal.output_digest != expected:
            raise ValueError(
                f"proposal {proposal.proposal_id} output_digest mismatch: "
                f"fixture={proposal.output_digest} recomputed={expected}"
            )
        replayed.append(proposal.model_copy(deep=True))
    return replayed


def save_proposal_fixture(path: Path | str, proposals: list[ModelProposal]) -> Path:
    """Write proposals to a deterministic JSON fixture."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "envassure.model_proposal.v1",
        "proposals": [p.model_dump(mode="json") for p in proposals],
    }
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


class StubProposalProvider:
    """
    Deterministic offline proposal provider (no live LLM).

    Looks up canned responses by prompt digest or exact prompt text. Suitable
    for CI and unit tests under the optional ``model-assisted`` extra surface.
    """

    def __init__(
        self,
        *,
        responses: dict[str, dict[str, Any]] | None = None,
        fixture_path: Path | str | None = None,
        model_id: str = "stub-provider-v0",
    ) -> None:
        self._model_id = model_id
        self._by_key: dict[str, dict[str, Any]] = dict(responses or {})
        if fixture_path is not None:
            raw = json.loads(Path(fixture_path).read_text(encoding="utf-8-sig"))
            if isinstance(raw, dict):
                items = raw.get("responses") or raw.get("proposals") or []
                default_model = str(raw.get("model_id") or model_id)
                self._model_id = default_model
            elif isinstance(raw, list):
                items = raw
            else:
                raise ValueError("stub fixture must be object or list")
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(
                    item.get("prompt_digest") or item.get("prompt") or item.get("proposal_id") or ""
                )
                if key:
                    self._by_key[key] = item

    @property
    def model_id(self) -> str:
        return self._model_id

    def complete(
        self,
        prompt: str,
        *,
        subject: str,
        predicate: str,
        value: Any = None,
        source_context: str | dict[str, Any] | None = None,
        untrusted_excerpts: list[str] | None = None,
    ) -> ModelProposal:
        """Return a non-authoritative proposal for *prompt* (offline)."""
        prompt_digest = _digest(prompt)
        hit = self._by_key.get(prompt_digest) or self._by_key.get(prompt)
        resolved_value = value
        if hit is not None:
            resolved_value = hit.get("value", value)
            subject = str(hit.get("subject") or subject)
            predicate = str(hit.get("predicate") or predicate)
        return propose(
            summary=f"stub response for {subject}",
            subject=subject,
            predicate=predicate,
            value=resolved_value if resolved_value is not None else {"stub": True},
            model_id=self._model_id,
            prompt_digest=prompt_digest,
            source_context=source_context,
            untrusted_excerpts=untrusted_excerpts,
        )


def set_review_disposition(
    proposal: ModelProposal,
    disposition: ReviewerDisposition,
    *,
    reviewer: str,
    reason: str | None = None,
) -> ModelProposal:
    """
    Apply a review disposition without elevating authority.

    Allowed transitions are recorded in metadata; ``accepted`` still requires
    ``promote_with_expert_decision`` before any source-fact treatment.
    """
    assert_not_authoritative(proposal)
    copy = proposal.model_copy(deep=True)
    copy.reviewer_disposition = disposition
    copy.metadata = {
        **copy.metadata,
        "reviewer": reviewer,
        "disposition_reason": reason,
        "disposition_at": datetime.now(UTC).isoformat(),
    }
    if disposition == "accepted":
        copy.accepted = True
        # Still non-authoritative: route through needs_expert_decision semantics.
        copy.reviewer_disposition = "needs_expert_decision"
        copy.metadata["reviewer_disposition_requested"] = "accepted"
    elif disposition in {"rejected", "deferred"}:
        copy.accepted = False
    return copy


def run_proposal_pipeline(
    prompt: str,
    *,
    subject: str,
    predicate: str,
    value: Any = None,
    source_context: str | dict[str, Any] | None = None,
    untrusted_excerpts: list[str] | None = None,
    provider: Any | None = None,
    model_id: str = "offline-pipeline",
) -> ModelProposal:
    """
    Recorded proposal pipeline: digest prompt/context, isolate untrusted text,
    emit a tainted ``model_proposal`` that cannot become a source fact until
    expert promotion.
    """
    if provider is not None:
        raw = provider.complete(
            prompt,
            subject=subject,
            predicate=predicate,
            value=value,
            source_context=source_context,
            untrusted_excerpts=untrusted_excerpts,
        )
        proposal = raw if isinstance(raw, ModelProposal) else ModelProposal.model_validate(raw)
    else:
        proposal = propose(
            summary=None,
            subject=subject,
            predicate=predicate,
            value=value,
            model_id=model_id,
            prompt_digest=_digest(prompt),
            source_context=source_context,
            untrusted_excerpts=untrusted_excerpts,
        )
    assert_not_authoritative(proposal)
    # Explicit taint isolation from source facts.
    proposal.isolation = {
        **proposal.isolation,
        "taint": "model_proposal",
        "isolated_from_source_facts": True,
        "prompt_injection_isolation": True,
    }
    proposal.metadata = {
        **proposal.metadata,
        "pipeline": "run_proposal_pipeline",
        "prompt_digest": proposal.prompt_digest,
        "auto_accept": False,
    }
    return proposal


# Lazy re-exports for provider packaging (avoid import cycles at module load).
def __getattr__(name: str) -> Any:
    if name in {
        "ProposalProvider",
        "get_provider",
        "list_provider_entry_points",
        "require_model_assisted_extra",
        "MODEL_ASSISTED_IMPORT_ERROR",
        "PROPOSAL_PROVIDER_ENTRY_GROUP",
    }:
        from envassure.model_assisted import providers as _providers

        return getattr(_providers, name)
    if name == "HttpProposalProvider":
        from envassure.model_assisted.http import HttpProposalProvider

        return HttpProposalProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "MODEL_ASSISTED_IMPORT_ERROR",
    "PROPOSAL_PROVIDER_ENTRY_GROUP",
    "HttpProposalProvider",
    "ModelProposal",
    "ProposalMetadata",
    "ProposalProvider",
    "ReviewerDisposition",
    "StubProposalProvider",
    "assert_not_authoritative",
    "get_provider",
    "list_provider_entry_points",
    "load_proposal_fixture",
    "mark_as_source_fact",
    "promote_with_expert_decision",
    "propose",
    "replay_accepted_proposals",
    "require_model_assisted_extra",
    "run_proposal_pipeline",
    "save_proposal_fixture",
    "set_review_disposition",
]
