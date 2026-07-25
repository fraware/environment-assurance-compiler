"""SQL DDL adapter → state aggregate facts from CREATE TABLE."""

from __future__ import annotations

import re
from pathlib import Path

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import SourceParseError

_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>(?:[`\"\[]?\w+[\]`\"]?|\w+))"
    r"\s*\((?P<body>.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_COLUMN = re.compile(
    r"^\s*(?P<name>(?:[`\"\[]?\w+[\]`\"]?|\w+))\s+(?P<type>\w+(?:\([^)]*\))?)",
    re.IGNORECASE,
)


class DatabaseAdapter:
    """Parse simple CREATE TABLE DDL into state aggregate facts."""

    kind = "database"

    def parse(self, path: Path) -> list[SemanticFact]:
        if not path.is_file():
            raise SourceParseError(path, "file not found")
        text = path.read_text(encoding="utf-8")
        matches = list(_CREATE_TABLE.finditer(text))
        if not matches:
            raise SourceParseError(path, "no CREATE TABLE statements found")

        source = str(path)
        confidence = ConfidenceRecord(
            evidence_class="database_schema",
            extractor_certainty="high",
        )
        facts: list[SemanticFact] = []
        for match in matches:
            table = _strip_ident(match.group("name"))
            body = match.group("body")
            columns = _parse_columns(body)
            subject = EntityRef(kind="state_aggregate", id=table)
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="state_aggregate",
                        subject_id=table,
                        predicate="is_aggregate",
                        source=source,
                    ),
                    subject=subject,
                    predicate="is_aggregate",
                    value=True,
                    source_refs=[source],
                    extraction_method="sql.create_table",
                    confidence=confidence,
                    kind_tags=["state", "aggregate"],
                )
            )
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="state_aggregate",
                        subject_id=table,
                        predicate="columns",
                        source=source,
                    ),
                    subject=subject,
                    predicate="columns",
                    value=columns,
                    source_refs=[source],
                    extraction_method="sql.create_table",
                    confidence=confidence,
                    kind_tags=["state", "aggregate"],
                )
            )
            for col in columns:
                col_subject = EntityRef(kind="state_variable", id=f"{table}.{col['name']}")
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="state_variable",
                            subject_id=col_subject.id,
                            predicate="column_type",
                            source=source,
                        ),
                        subject=col_subject,
                        predicate="column_type",
                        value=col["type"],
                        source_refs=[source],
                        extraction_method="sql.create_table.column",
                        confidence=confidence,
                        kind_tags=["state", "column"],
                    )
                )
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="state_variable",
                            subject_id=col_subject.id,
                            predicate="owning_aggregate",
                            source=source,
                        ),
                        subject=col_subject,
                        predicate="owning_aggregate",
                        value=table,
                        source_refs=[source],
                        extraction_method="sql.create_table.column",
                        confidence=confidence,
                        kind_tags=["state", "column"],
                    )
                )
        return facts


def _strip_ident(name: str) -> str:
    return name.strip().strip('`"[]')


def _parse_columns(body: str) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for part in body.split(","):
        line = part.strip()
        if not line:
            continue
        upper = line.upper()
        if upper.startswith(
            ("PRIMARY KEY", "UNIQUE", "CONSTRAINT", "FOREIGN KEY", "CHECK", "INDEX")
        ):
            continue
        match = _COLUMN.match(line)
        if match is None:
            continue
        columns.append(
            {
                "name": _strip_ident(match.group("name")),
                "type": match.group("type").upper(),
            }
        )
    return columns
