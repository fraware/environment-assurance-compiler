"""Streaming JSONL trace adapter → operational facts (memory-bounded)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import SourceParseError


class TraceAdapter:
    """Ingest operational traces line-by-line without loading the whole file.

    Per-event observations are represented as ``trace_event`` facts rather than
    action-level semantic claims. Action-level operational semantics are emitted
    only when the trace supports an explicit inference (for example, a commit
    observed after a correlated timeout makes an unconditional retry unsafe).
    """

    kind = "traces"

    def parse(self, path: Path) -> list[SemanticFact]:
        if not path.is_file():
            raise SourceParseError(path, "file not found")
        facts: list[SemanticFact] = []
        source = str(path)
        observed_confidence = ConfidenceRecord(
            evidence_class="operational_trace",
            derivation_class="observed",
            extractor_certainty="medium",
        )
        event_count = 0
        timed_out_attempts: set[tuple[str, str | None]] = set()
        for line_no, event in _iter_jsonl(path):
            event_count += 1
            facts.extend(
                _facts_from_event(
                    event=event,
                    line_no=line_no,
                    source=source,
                    observed_confidence=observed_confidence,
                    timed_out_attempts=timed_out_attempts,
                )
            )
        if event_count == 0:
            raise SourceParseError(path, "empty or non-JSONL trace")
        # Aggregate summary fact — counts only, not full payload retention.
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind="trace",
                    subject_id=path.stem,
                    predicate="event_count",
                    source=source,
                ),
                subject=EntityRef(kind="trace", id=path.stem),
                predicate="event_count",
                value=event_count,
                source_refs=[source],
                extraction_method="traces.jsonl.stream",
                confidence=observed_confidence,
                kind_tags=["trace", "operational"],
            )
        )
        return facts


def _iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    """Yield (line_number, event) streaming one line at a time."""
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SourceParseError(path, f"line {line_no}: invalid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise SourceParseError(path, f"line {line_no}: event must be a JSON object")
            yield line_no, payload


def _trace_event_id(*, source: str, line_no: int) -> str:
    """Return a stable-in-workspace id for one source event without exposing its path."""
    source_key = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return f"{source_key}:{line_no}"


def _attempt_correlation(event: dict[str, Any]) -> str | None:
    """Return an explicit attempt correlation id when the trace provides one.

    We intentionally do not synthesize correlation across separately identified
    requests. When no correlation field exists, ``None`` permits only the weaker
    within-action temporal heuristic for traces that genuinely lack identifiers.
    """
    for key in ("request_id", "correlation_id", "trace_id", "span_id"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return f"{key}:{value.strip()}"
    return None


def _facts_from_event(
    *,
    event: dict[str, Any],
    line_no: int,
    source: str,
    observed_confidence: ConfidenceRecord,
    timed_out_attempts: set[tuple[str, str | None]],
) -> list[SemanticFact]:
    facts: list[SemanticFact] = []
    action_id = event.get("action") or event.get("action_id") or event.get("op")
    if not isinstance(action_id, str) or not action_id.strip():
        return facts

    action = EntityRef(kind="action", id=action_id.strip())
    event_subject = EntityRef(
        kind="trace_event",
        id=_trace_event_id(source=source, line_no=line_no),
    )
    event_source_ref = f"{source}:{line_no}"
    attempt = (action.id, _attempt_correlation(event))

    # Link the event to the action explicitly. Observations belong to this event,
    # not to the action's canonical semantic definition.
    facts.append(
        SemanticFact(
            fact_id=make_fact_id(
                subject_kind=event_subject.kind,
                subject_id=event_subject.id,
                predicate="observed_action",
                source=source,
                suffix=str(line_no),
            ),
            subject=event_subject,
            predicate="observed_action",
            value=action.id,
            source_refs=[event_source_ref],
            extraction_method="traces.jsonl.event",
            confidence=observed_confidence,
            kind_tags=["trace_event", "action", "operational"],
        )
    )

    outcome = event.get("outcome") or event.get("status") or event.get("result")
    if outcome is not None:
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=event_subject.kind,
                    subject_id=event_subject.id,
                    predicate="observed_outcome",
                    source=source,
                    suffix=str(line_no),
                ),
                subject=event_subject,
                predicate="observed_outcome",
                value=outcome,
                source_refs=[event_source_ref],
                extraction_method="traces.jsonl.event",
                confidence=observed_confidence,
                kind_tags=["trace_event", "outcome", "operational"],
            )
        )

    is_timeout = event.get("timeout") is True or str(outcome).lower() in {
        "timeout",
        "gateway_timeout",
        "504",
    }
    if is_timeout:
        timed_out_attempts.add(attempt)
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=event_subject.kind,
                    subject_id=event_subject.id,
                    predicate="observed_timeout",
                    source=source,
                    suffix=str(line_no),
                ),
                subject=event_subject,
                predicate="observed_timeout",
                value=True,
                source_refs=[event_source_ref],
                extraction_method="traces.jsonl.timeout",
                confidence=observed_confidence,
                kind_tags=["trace_event", "timeout", "operational"],
            )
        )

    state_effect = event.get("state_effect") or event.get("authoritative_state")
    if state_effect is not None:
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=event_subject.kind,
                    subject_id=event_subject.id,
                    predicate="observed_state_effect",
                    source=source,
                    suffix=str(line_no),
                ),
                subject=event_subject,
                predicate="observed_state_effect",
                value=state_effect,
                source_refs=[event_source_ref],
                extraction_method="traces.jsonl.state",
                confidence=observed_confidence,
                kind_tags=["trace_event", "state", "operational"],
            )
        )

        # A commit correlated to a prior timeout supports a safety inference
        # about retry policy. A separately identified later request must not
        # inherit the timeout merely because it has the same action id.
        if attempt in timed_out_attempts and str(state_effect).lower() in {
            "committed",
            "refund_committed",
            "applied",
        }:
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="action",
                        subject_id=action.id,
                        predicate="retry_behavior",
                        source=source,
                        suffix=f"unsafe:{line_no}",
                    ),
                    subject=action,
                    predicate="retry_behavior",
                    value="do_not_retry_without_idempotency_key",
                    source_refs=[event_source_ref],
                    extraction_method="traces.jsonl.retry_inference",
                    confidence=ConfidenceRecord(
                        evidence_class="operational_trace",
                        derivation_class="inferred",
                        extractor_certainty="medium",
                        notes="commit observed after a correlated timeout",
                    ),
                    kind_tags=["action", "retry", "trace", "inferred"],
                )
            )
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="action",
                        subject_id=action.id,
                        predicate="retry_guard_requirement",
                        source=source,
                        suffix=str(line_no),
                    ),
                    subject=action,
                    predicate="retry_guard_requirement",
                    value="idempotency_key",
                    source_refs=[event_source_ref],
                    extraction_method="traces.jsonl.idempotency_inference",
                    confidence=ConfidenceRecord(
                        evidence_class="operational_trace",
                        derivation_class="inferred",
                        extractor_certainty="low",
                        notes="guard inferred from commit after a correlated timeout",
                    ),
                    kind_tags=["action", "idempotency", "trace", "inferred"],
                )
            )
    return facts
