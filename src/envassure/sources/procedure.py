"""Markdown SOP / procedure adapter → procedure facts from headings."""

from __future__ import annotations

import re
from pathlib import Path

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import SourceParseError

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_RETRY_HINT = re.compile(r"\bretr(?:y|ies|ying)\b", re.IGNORECASE)
_TIMEOUT_HINT = re.compile(r"\btimeouts?\b", re.IGNORECASE)
_IDEMPOTENCY_HINT = re.compile(r"\bidempoten", re.IGNORECASE)


class ProcedureAdapter:
    """Parse markdown SOP headings/sections into procedure facts."""

    kind = "procedure"

    def parse(self, path: Path) -> list[SemanticFact]:
        if not path.is_file():
            raise SourceParseError(path, "file not found")
        lines = path.read_text(encoding="utf-8").splitlines()
        sections = _split_sections(lines)
        if not sections:
            raise SourceParseError(path, "no markdown headings found")

        source = str(path)
        confidence = ConfidenceRecord(
            evidence_class="approved_procedure",
            extractor_certainty="medium",
        )
        facts: list[SemanticFact] = []
        doc_id = path.stem
        doc_subject = EntityRef(kind="procedure", id=doc_id)
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind="procedure",
                    subject_id=doc_id,
                    predicate="is_procedure",
                    source=source,
                ),
                subject=doc_subject,
                predicate="is_procedure",
                value=True,
                source_refs=[source],
                extraction_method="markdown.sop",
                confidence=confidence,
                kind_tags=["procedure"],
            )
        )

        for index, section in enumerate(sections):
            section_id = f"{doc_id}#{_slug(section['title'])}"
            subject = EntityRef(kind="procedure_section", id=section_id)
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="procedure_section",
                        subject_id=section_id,
                        predicate="section_heading",
                        source=source,
                        suffix=str(index),
                    ),
                    subject=subject,
                    predicate="section_heading",
                    value={
                        "level": section["level"],
                        "title": section["title"],
                        "body": section["body"],
                    },
                    source_refs=[source],
                    extraction_method="markdown.heading",
                    confidence=confidence,
                    kind_tags=["procedure", "section"],
                )
            )
            body = section["body"]
            title = section["title"]
            combined = f"{title}\n{body}"

            # Bind operational semantics mentioned in SOP text to nearby action ids.
            action_id = _infer_action_id(title, body)
            if action_id is not None:
                action = EntityRef(kind="action", id=action_id)
                if _RETRY_HINT.search(combined):
                    facts.append(
                        SemanticFact(
                            fact_id=make_fact_id(
                                subject_kind="action",
                                subject_id=action_id,
                                predicate="retry_behavior",
                                source=source,
                            ),
                            subject=action,
                            predicate="retry_behavior",
                            value=_extract_retry_value(combined),
                            source_refs=[source],
                            extraction_method="markdown.sop.retry",
                            confidence=ConfidenceRecord(
                                evidence_class="approved_procedure",
                                extractor_certainty="medium",
                            ),
                            kind_tags=["action", "retry", "procedure"],
                        )
                    )
                if _TIMEOUT_HINT.search(combined):
                    facts.append(
                        SemanticFact(
                            fact_id=make_fact_id(
                                subject_kind="action",
                                subject_id=action_id,
                                predicate="timeout_behavior",
                                source=source,
                            ),
                            subject=action,
                            predicate="timeout_behavior",
                            value="sop_acknowledges_timeout",
                            source_refs=[source],
                            extraction_method="markdown.sop.timeout",
                            confidence=ConfidenceRecord(
                                evidence_class="approved_procedure",
                                extractor_certainty="low",
                            ),
                            kind_tags=["action", "timeout", "procedure"],
                        )
                    )
                if _IDEMPOTENCY_HINT.search(combined):
                    facts.append(
                        SemanticFact(
                            fact_id=make_fact_id(
                                subject_kind="action",
                                subject_id=action_id,
                                predicate="idempotency",
                                source=source,
                            ),
                            subject=action,
                            predicate="idempotency",
                            value="sop_mentions_idempotency",
                            source_refs=[source],
                            extraction_method="markdown.sop.idempotency",
                            confidence=ConfidenceRecord(
                                evidence_class="approved_procedure",
                                extractor_certainty="low",
                            ),
                            kind_tags=["action", "idempotency", "procedure"],
                        )
                    )
        return facts


def _split_sections(lines: list[str]) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    body_lines: list[str] = []
    for line in lines:
        match = _HEADING.match(line)
        if match:
            if current is not None:
                current["body"] = "\n".join(body_lines).strip()
                sections.append(current)
            current = {
                "level": len(match.group(1)),
                "title": match.group(2).strip(),
            }
            body_lines = []
        elif current is not None:
            body_lines.append(line)
    if current is not None:
        current["body"] = "\n".join(body_lines).strip()
        sections.append(current)
    return sections


def _slug(title: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", title.strip().lower()).strip("_")
    return cleaned or "section"


def _infer_action_id(title: str, body: str) -> str | None:
    """Infer an action id from SOP text (e.g. submit_refund)."""
    combined = f"{title} {body}"
    # Prefer explicit snake_case action tokens.
    match = re.search(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", combined)
    if match:
        return match.group(1)
    # Fallback: title words joined.
    words = re.findall(r"[A-Za-z0-9]+", title.lower())
    if len(words) >= 2:
        return "_".join(words)
    return None


def _extract_retry_value(text: str) -> str:
    if re.search(r"\bdo not retry\b|\bnever retry\b", text, re.IGNORECASE):
        return "do_not_retry"
    if re.search(r"\bretry\b", text, re.IGNORECASE):
        return "retry_on_timeout"
    return "retry_mentioned"
