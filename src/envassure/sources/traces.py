"""Streaming JSONL trace adapter → operational facts (memory-bounded)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import SourceParseError


class TraceAdapter:
    """Ingest operational traces line-by-line without loading the whole file."""

    kind = "traces"

    def parse(self, path: Path) -> list[SemanticFact]:
        if not path.is_file():
            raise SourceParseError(path, "file not found")
        facts: list[SemanticFact] = []
        source = str(path)
        confidence = ConfidenceRecord(
            evidence_class="operational_trace",
            extractor_certainty="medium",
        )
        event_count = 0
        for line_no, event in _iter_jsonl(path):
            event_count += 1
            facts.extend(
                _facts_from_event(
                    event=event,
                    line_no=line_no,
                    source=source,
                    confidence=confidence,
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
                confidence=confidence,
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


def _facts_from_event(
    *,
    event: dict[str, Any],
    line_no: int,
    source: str,
    confidence: ConfidenceRecord,
) -> list[SemanticFact]:
    facts: list[SemanticFact] = []
    action_id = event.get("action") or event.get("action_id") or event.get("op")
    if isinstance(action_id, str) and action_id.strip():
        subject = EntityRef(kind="action", id=action_id.strip())
        outcome = event.get("outcome") or event.get("status") or event.get("result")
        if outcome is not None:
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="action",
                        subject_id=subject.id,
                        predicate="observed_outcome",
                        source=source,
                        suffix=str(line_no),
                    ),
                    subject=subject,
                    predicate="observed_outcome",
                    value=outcome,
                    source_refs=[f"{source}:{line_no}"],
                    extraction_method="traces.jsonl.event",
                    confidence=confidence,
                    kind_tags=["action", "operational", "trace"],
                )
            )
        # Timeout then commit pattern — critical for refund conflict demo.
        if event.get("timeout") is True or str(outcome).lower() in {
            "timeout",
            "gateway_timeout",
            "504",
        }:
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="action",
                        subject_id=subject.id,
                        predicate="timeout_behavior",
                        source=source,
                        suffix=f"obs:{line_no}",
                    ),
                    subject=subject,
                    predicate="timeout_behavior",
                    value="observed_timeout",
                    source_refs=[f"{source}:{line_no}"],
                    extraction_method="traces.jsonl.timeout",
                    confidence=confidence,
                    kind_tags=["action", "timeout", "trace"],
                )
            )
        state_effect = event.get("state_effect") or event.get("authoritative_state")
        if state_effect is not None:
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="action",
                        subject_id=subject.id,
                        predicate="observed_state_effect",
                        source=source,
                        suffix=str(line_no),
                    ),
                    subject=subject,
                    predicate="observed_state_effect",
                    value=state_effect,
                    source_refs=[f"{source}:{line_no}"],
                    extraction_method="traces.jsonl.state",
                    confidence=confidence,
                    kind_tags=["action", "state", "trace"],
                )
            )
            # Committed after timeout → retry may double-apply.
            if str(state_effect).lower() in {"committed", "refund_committed", "applied"}:
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="action",
                            subject_id=subject.id,
                            predicate="retry_behavior",
                            source=source,
                            suffix=f"unsafe:{line_no}",
                        ),
                        subject=subject,
                        predicate="retry_behavior",
                        value="unsafe_without_idempotency_key",
                        source_refs=[f"{source}:{line_no}"],
                        extraction_method="traces.jsonl.retry_inference",
                        confidence=ConfidenceRecord(
                            evidence_class="operational_trace",
                            extractor_certainty="medium",
                        ),
                        kind_tags=["action", "retry", "trace"],
                    )
                )
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="action",
                            subject_id=subject.id,
                            predicate="idempotency",
                            source=source,
                            suffix=str(line_no),
                        ),
                        subject=subject,
                        predicate="idempotency",
                        value="required_but_unspecified",
                        source_refs=[f"{source}:{line_no}"],
                        extraction_method="traces.jsonl.idempotency_inference",
                        confidence=ConfidenceRecord(
                            evidence_class="operational_trace",
                            extractor_certainty="low",
                        ),
                        kind_tags=["action", "idempotency", "trace"],
                    )
                )
    return facts
