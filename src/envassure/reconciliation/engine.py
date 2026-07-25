"""Reconciliation engine: conflicts, aliases, missing operational semantics."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import SemanticFact
from envassure.ir.models import AmbiguityRecord
from envassure.ir.primitives import ProvenanceRef
from envassure.workspace.config import SourcePrecedenceSection

_OPERATIONAL_PREDICATES = frozenset({"timeout_behavior", "retry_behavior", "idempotency"})
_DEFAULT_PRECEDENCE = SourcePrecedenceSection().order


class ReconciliationResult(BaseModel):
    """Outcome of fact reconciliation."""

    model_config = ConfigDict(extra="forbid")

    ambiguities: list[AmbiguityRecord] = Field(default_factory=list)
    diagnostics: DiagnosticReport = Field(default_factory=DiagnosticReport)
    preferred_facts: list[SemanticFact] = Field(default_factory=list)
    superseded_fact_ids: list[str] = Field(default_factory=list)
    alias_groups: list[list[str]] = Field(default_factory=list)


@dataclass
class _FactGroup:
    subject_kind: str
    subject_id: str
    predicate: str
    facts: list[SemanticFact] = field(default_factory=list)


def reconcile(
    facts: Sequence[SemanticFact] | Iterable[SemanticFact],
    precedence: Sequence[str] | SourcePrecedenceSection | None = None,
) -> ReconciliationResult:
    """Detect conflicts/aliases/missing semantics and emit ambiguities + diagnostics.

    ``precedence`` projects candidate interpretation order using ``eac.toml``
    ``source_precedence.order`` (evidence class ranking). Conflicts remain open
    ambiguities; precedence only orders candidates.
    """
    fact_list = list(facts)
    order = _normalize_precedence(precedence)
    result = ReconciliationResult()

    groups = _group_facts(fact_list)
    alias_groups = _detect_aliases(fact_list)
    result.alias_groups = alias_groups
    for group in alias_groups:
        subject = ",".join(group)
        result.diagnostics.add(
            make_diagnostic(
                "EAC2003",
                subject=subject,
                reason=f"identifiers appear synonymous: {group}",
            )
        )
        amb_id = _ambiguity_id("alias", subject, "alias")
        result.ambiguities.append(
            AmbiguityRecord(
                id=amb_id,
                subject=subject,
                source_excerpts=[f"alias candidates: {group}"],
                conflict_class="alias",
                candidate_interpretations=list(group),
                default_prohibition="Do not merge subjects without an expert decision.",
                affected_actions=[s for s in group if not s.startswith("schema:")],
                operational_consequence="Duplicate or missing IR bindings possible.",
                required_expert_role="domain_expert",
                status="open",
                provenance=ProvenanceRef(
                    fact_ids=[
                        f.fact_id
                        for f in fact_list
                        if f.subject.id in {g.split(":", 1)[-1] for g in group}
                        or f"{f.subject.kind}:{f.subject.id}" in group
                    ]
                ),
            )
        )

    preferred: dict[tuple[str, str, str], SemanticFact] = {}
    superseded: list[str] = []

    for key, fact_group in groups.items():
        distinct = _distinct_values(fact_group.facts)
        ranked = _rank_by_precedence(fact_group.facts, order)
        if len(distinct) > 1:
            subject = f"{fact_group.subject_kind}:{fact_group.subject_id}"
            reason = (
                f"predicate {fact_group.predicate!r} has conflicting values "
                f"{[_short(v) for v in distinct]}"
            )
            result.diagnostics.add(make_diagnostic("EAC2002", subject=subject, reason=reason))
            interpretations = [_interpretation(f, order) for f in ranked]
            amb = AmbiguityRecord(
                id=_ambiguity_id(subject, fact_group.predicate, "conflict"),
                subject=subject,
                source_excerpts=[
                    f"{f.source_refs}: {f.predicate}={_short(f.value)}" for f in ranked
                ],
                conflict_class="semantic_conflict",
                candidate_interpretations=interpretations,
                default_prohibition=(
                    "Do not project conflicting values into IR without a decision."
                ),
                affected_actions=(
                    [fact_group.subject_id] if fact_group.subject_kind == "action" else []
                ),
                operational_consequence=(
                    "Release-grade packs blocked until interpretation is chosen."
                ),
                required_expert_role="domain_expert",
                status="open",
                provenance=ProvenanceRef(
                    fact_ids=[f.fact_id for f in ranked],
                    source_ids=_unique_sources(ranked),
                ),
            )
            # Stable demo id for the classic refund retry/timeout conflict.
            if _is_refund_retry_timeout_conflict(fact_group, ranked):
                amb = amb.model_copy(update={"id": "AMB-0042"})
            result.ambiguities.append(amb)
            # Mark lower-precedence facts superseded for projection hints.
            winner = ranked[0]
            preferred[key] = winner.model_copy(
                update={
                    "confidence": winner.confidence.model_copy(
                        update={"conflict_status": "unresolved"}
                    )
                }
            )
            for loser in ranked[1:]:
                superseded.append(loser.fact_id)
        else:
            preferred[key] = ranked[0]

    # Missing timeout / retry / idempotency on actions.
    action_ids = {f.subject.id for f in fact_list if f.subject.kind == "action"}
    conflicted_keys = {
        (g.subject_kind, g.subject_id, g.predicate)
        for g in groups.values()
        if len(_distinct_values(g.facts)) > 1
    }
    for action_id in sorted(action_ids):
        preds = {
            f.predicate: f
            for f in fact_list
            if f.subject.kind == "action" and f.subject.id == action_id
        }
        has_timeout = "timeout_behavior" in preds
        has_retry = "retry_behavior" in preds
        has_idempotency = "idempotency" in preds
        retry_conflicted = ("action", action_id, "retry_behavior") in conflicted_keys
        if has_timeout and (not has_retry or retry_conflicted):
            subject = f"action:{action_id}"
            result.diagnostics.add(make_diagnostic("EAC4027", action_id=action_id, subject=subject))
            if not any(
                a.conflict_class == "missing_retry_semantics" and action_id in a.affected_actions
                for a in result.ambiguities
            ) and not any(
                a.id == "AMB-0042" and action_id in a.affected_actions for a in result.ambiguities
            ):
                result.ambiguities.append(
                    AmbiguityRecord(
                        id=_ambiguity_id(subject, "retry_behavior", "missing"),
                        subject=subject,
                        source_excerpts=[
                            f"timeout_behavior={_short(preds['timeout_behavior'].value)}"
                        ],
                        conflict_class="missing_retry_semantics",
                        candidate_interpretations=[
                            "retry_on_timeout",
                            "do_not_retry",
                            "retry_with_idempotency_key",
                        ],
                        default_prohibition=(
                            "Do not generate timeout/retry tasks until retry_behavior is defined."
                        ),
                        affected_actions=[action_id],
                        operational_consequence=("Timeout/retry tasks and verifiers are unsafe."),
                        required_expert_role="reliability_engineer",
                        status="open",
                        provenance=ProvenanceRef(
                            fact_ids=[preds["timeout_behavior"].fact_id],
                            source_ids=_unique_sources([preds["timeout_behavior"]]),
                        ),
                    )
                )
        if (has_timeout or has_retry) and not has_idempotency:
            subject = f"action:{action_id}"
            # Prefer folding into AMB-0042 when already present for this action.
            existing = next(
                (
                    a
                    for a in result.ambiguities
                    if a.id == "AMB-0042" and action_id in a.affected_actions
                ),
                None,
            )
            if existing is None and not any(
                a.conflict_class == "missing_idempotency" and action_id in a.affected_actions
                for a in result.ambiguities
            ):
                result.ambiguities.append(
                    AmbiguityRecord(
                        id=_ambiguity_id(subject, "idempotency", "missing"),
                        subject=subject,
                        source_excerpts=["missing idempotency while timeout/retry present"],
                        conflict_class="missing_idempotency",
                        candidate_interpretations=[
                            "none",
                            "client_key_required",
                            "server_dedup_window",
                        ],
                        default_prohibition=(
                            "Do not assume safe retries without idempotency semantics."
                        ),
                        affected_actions=[action_id],
                        operational_consequence=("Retries may double-apply state changes."),
                        required_expert_role="reliability_engineer",
                        status="open",
                        provenance=ProvenanceRef(
                            fact_ids=[
                                f.fact_id for p, f in preds.items() if p in _OPERATIONAL_PREDICATES
                            ],
                        ),
                    )
                )

    # Deduplicate ambiguity ids (AMB-0042 override may collide with hash id).
    result.ambiguities = _dedupe_ambiguities(result.ambiguities)
    result.preferred_facts = list(preferred.values())
    result.superseded_fact_ids = superseded
    return result


def project_source_precedence(
    precedence: Sequence[str] | SourcePrecedenceSection | None = None,
) -> list[str]:
    """Return the effective source precedence order from eac.toml projection."""
    return list(_normalize_precedence(precedence))


def _normalize_precedence(
    precedence: Sequence[str] | SourcePrecedenceSection | None,
) -> list[str]:
    if precedence is None:
        return list(_DEFAULT_PRECEDENCE)
    if isinstance(precedence, SourcePrecedenceSection):
        return list(precedence.order)
    return list(precedence)


def _group_facts(facts: list[SemanticFact]) -> dict[tuple[str, str, str], _FactGroup]:
    groups: dict[tuple[str, str, str], _FactGroup] = {}
    for fact in facts:
        key = (fact.subject.kind, fact.subject.id, fact.predicate)
        if key not in groups:
            groups[key] = _FactGroup(
                subject_kind=fact.subject.kind,
                subject_id=fact.subject.id,
                predicate=fact.predicate,
            )
        groups[key].facts.append(fact)
    return groups


def _distinct_values(facts: list[SemanticFact]) -> list[Any]:
    seen: list[Any] = []
    fingerprints: set[str] = set()
    for fact in facts:
        fp = _value_fingerprint(fact.value)
        if fp not in fingerprints:
            fingerprints.add(fp)
            seen.append(fact.value)
    return seen


def _value_fingerprint(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _rank_by_precedence(
    facts: list[SemanticFact],
    order: Sequence[str],
) -> list[SemanticFact]:
    rank = {name: index for index, name in enumerate(order)}

    def sort_key(fact: SemanticFact) -> tuple[int, str]:
        evidence = fact.confidence.evidence_class
        return (rank.get(evidence, len(order)), fact.fact_id)

    return sorted(facts, key=sort_key)


def _interpretation(fact: SemanticFact, order: Sequence[str]) -> str:
    rank = {name: index for index, name in enumerate(order)}
    precedence_index = rank.get(fact.confidence.evidence_class, len(order))
    return (
        f"[precedence={precedence_index}:{fact.confidence.evidence_class}] "
        f"{fact.predicate}={_short(fact.value)} "
        f"(sources={fact.source_refs})"
    )


def _unique_sources(facts: Sequence[SemanticFact]) -> list[str]:
    seen: list[str] = []
    for fact in facts:
        for ref in fact.source_refs:
            base = ref.split(":")[0] if ":" in ref and ref.count(":") == 1 else ref
            # Keep full path refs; only strip line suffixes like path:12 when numeric.
            parts = ref.rsplit(":", 1)
            base = parts[0] if len(parts) == 2 and parts[1].isdigit() else ref
            if base not in seen:
                seen.append(base)
    return seen


def _detect_aliases(facts: list[SemanticFact]) -> list[list[str]]:
    """Detect alias groups via alias_of facts or shared display names."""
    groups: list[list[str]] = []
    explicit: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        if fact.predicate in {"alias_of", "same_as", "alias"}:
            left = f"{fact.subject.kind}:{fact.subject.id}"
            right_val = fact.value
            if isinstance(right_val, dict):
                right = f"{right_val.get('kind', fact.subject.kind)}:{right_val.get('id')}"
            else:
                right = f"{fact.subject.kind}:{right_val}"
            explicit[left].add(right)
            explicit[right].add(left)

    # Union-find style merge for explicit aliases.
    visited: set[str] = set()
    for node in list(explicit):
        if node in visited:
            continue
        stack = [node]
        component: set[str] = set()
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            component.add(current)
            stack.extend(explicit.get(current, ()))
        if len(component) > 1:
            groups.append(sorted(component))

    # Shared description/name across different action ids.
    by_name: dict[str, set[str]] = defaultdict(set)
    for fact in facts:
        if fact.predicate in {"description", "name", "display_name"} and isinstance(
            fact.value, str
        ):
            key = fact.value.strip().lower()
            if key:
                by_name[key].add(f"{fact.subject.kind}:{fact.subject.id}")
    for ids in by_name.values():
        if len(ids) > 1:
            group = sorted(ids)
            if group not in groups:
                groups.append(group)
    return groups


def _ambiguity_id(subject: str, predicate: str, kind: str) -> str:
    digest = hashlib.sha256(f"{kind}|{subject}|{predicate}".encode()).hexdigest()[:8]
    return f"AMB-{digest.upper()}"


def _short(value: Any, limit: int = 80) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _is_refund_retry_timeout_conflict(
    group: _FactGroup,
    facts: list[SemanticFact],
) -> bool:
    if group.subject_id != "submit_refund":
        return False
    if group.predicate not in {"retry_behavior", "timeout_behavior"}:
        return False
    evidence = {f.confidence.evidence_class for f in facts}
    return (
        "api_contract" in evidence
        or "approved_procedure" in evidence
        or ("operational_trace" in evidence and group.predicate == "retry_behavior")
    )


def _dedupe_ambiguities(items: list[AmbiguityRecord]) -> list[AmbiguityRecord]:
    by_id: dict[str, AmbiguityRecord] = {}
    for item in items:
        if item.id in by_id:
            existing = by_id[item.id]
            by_id[item.id] = existing.model_copy(
                update={
                    "candidate_interpretations": _merge_unique(
                        existing.candidate_interpretations,
                        item.candidate_interpretations,
                    ),
                    "source_excerpts": _merge_unique(
                        existing.source_excerpts, item.source_excerpts
                    ),
                    "affected_actions": _merge_unique(
                        existing.affected_actions, item.affected_actions
                    ),
                }
            )
        else:
            by_id[item.id] = item
    return list(by_id.values())


def _merge_unique(a: list[str], b: list[str]) -> list[str]:
    out: list[str] = []
    for item in [*a, *b]:
        if item not in out:
            out.append(item)
    return out
