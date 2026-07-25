"""Postgres-oriented DDL → SemanticFact extraction (offline-friendly).

Parsing is pure regex/string work and does not open a database. Construction
of :class:`PostgresDDLAdapter` still requires the ``[postgres]`` extra so the
feature surface fails closed when the optional dependency is absent.
"""

from __future__ import annotations

import re
from pathlib import Path

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.postgres._extra import require_postgres_extra
from envassure.sources.base import SourceParseError

# Schema-qualified or bare identifiers, optionally quoted.
_IDENT = r'(?:(?:"[^"]+"|[A-Za-z_][\w$]*)\.)?(?:"[^"]+"|[A-Za-z_][\w$]*)'

_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    rf"(?P<name>{_IDENT})"
    r"\s*\((?P<body>.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)

_COLUMN = re.compile(
    r"^\s*(?P<name>\"[^\"]+\"|[A-Za-z_][\w$]*)\s+"
    r"(?P<type>"
    r"DOUBLE\s+PRECISION|TIMESTAMPTZ|TIMESTAMP(?:\s+WITH(?:OUT)?\s+TIME\s+ZONE)?"
    r"|CHARACTER\s+VARYING|BIGINT|BIGSERIAL|SERIAL|SMALLSERIAL|UUID|JSONB|JSON"
    r"|TEXT|INTEGER|INT|SMALLINT|BOOLEAN|BOOL|REAL|NUMERIC(?:\([^)]*\))?"
    r"|VARCHAR(?:\([^)]*\))?|CHAR(?:\([^)]*\))?|BYTEA"
    r"|\w+(?:\([^)]*\))?)",
    re.IGNORECASE,
)

_CONSTRAINT_PREFIXES = (
    "PRIMARY KEY",
    "UNIQUE",
    "CONSTRAINT",
    "FOREIGN KEY",
    "CHECK",
    "INDEX",
    "EXCLUDE",
    "LIKE",
)

# Normalize common Postgres type spellings for stable fact values.
_TYPE_ALIASES: dict[str, str] = {
    "INT": "INTEGER",
    "BOOL": "BOOLEAN",
    "CHARACTER VARYING": "VARCHAR",
    "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
    "TIMESTAMPZ": "TIMESTAMP WITH TIME ZONE",
}


def parse_postgres_ddl(text: str) -> list[dict[str, object]]:
    """Parse Postgres-flavoured ``CREATE TABLE`` statements into table dicts.

    Each dict has ``name`` (possibly ``schema.table``), ``schema``, ``table``,
    and ``columns`` (list of ``{name, type}``). Does not require psycopg.
    """
    tables: list[dict[str, object]] = []
    for match in _CREATE_TABLE.finditer(text):
        raw_name = _strip_ident(match.group("name"))
        schema, table = _split_qualified(raw_name)
        columns = _parse_columns(match.group("body"))
        tables.append(
            {
                "name": raw_name,
                "schema": schema,
                "table": table,
                "columns": columns,
            }
        )
    return tables


class PostgresDDLAdapter:
    """Parse Postgres DDL into state aggregate facts.

    Requires the ``[postgres]`` extra at construction time (fail-closed).
    """

    kind = "postgres"

    def __init__(self) -> None:
        require_postgres_extra()

    def parse(self, path: Path) -> list[SemanticFact]:
        if not path.is_file():
            raise SourceParseError(path, "file not found")
        text = path.read_text(encoding="utf-8")
        tables = parse_postgres_ddl(text)
        if not tables:
            raise SourceParseError(path, "no CREATE TABLE statements found")

        source = str(path)
        confidence = ConfidenceRecord(
            evidence_class="database_schema",
            extractor_certainty="high",
            notes="postgres_ddl",
        )
        facts: list[SemanticFact] = []
        for table_info in tables:
            table_id = str(table_info["name"])
            schema = table_info.get("schema")
            columns = table_info["columns"]
            assert isinstance(columns, list)
            subject = EntityRef(kind="state_aggregate", id=table_id)
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="state_aggregate",
                        subject_id=table_id,
                        predicate="is_aggregate",
                        source=source,
                    ),
                    subject=subject,
                    predicate="is_aggregate",
                    value=True,
                    source_refs=[source],
                    extraction_method="postgres.create_table",
                    confidence=confidence,
                    kind_tags=["state", "aggregate", "postgres"],
                )
            )
            if schema:
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="state_aggregate",
                            subject_id=table_id,
                            predicate="schema_name",
                            source=source,
                        ),
                        subject=subject,
                        predicate="schema_name",
                        value=schema,
                        source_refs=[source],
                        extraction_method="postgres.create_table",
                        confidence=confidence,
                        kind_tags=["state", "aggregate", "postgres"],
                    )
                )
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="state_aggregate",
                        subject_id=table_id,
                        predicate="columns",
                        source=source,
                    ),
                    subject=subject,
                    predicate="columns",
                    value=columns,
                    source_refs=[source],
                    extraction_method="postgres.create_table",
                    confidence=confidence,
                    kind_tags=["state", "aggregate", "postgres"],
                )
            )
            for col in columns:
                assert isinstance(col, dict)
                col_name = str(col["name"])
                col_type = str(col["type"])
                col_subject = EntityRef(kind="state_variable", id=f"{table_id}.{col_name}")
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
                        value=col_type,
                        source_refs=[source],
                        extraction_method="postgres.create_table.column",
                        confidence=confidence,
                        kind_tags=["state", "column", "postgres"],
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
                        value=table_id,
                        source_refs=[source],
                        extraction_method="postgres.create_table.column",
                        confidence=confidence,
                        kind_tags=["state", "column", "postgres"],
                    )
                )
        return facts


def _strip_ident(name: str) -> str:
    parts = [p.strip().strip('"') for p in name.split(".")]
    return ".".join(parts)


def _split_qualified(name: str) -> tuple[str | None, str]:
    if "." in name:
        schema, table = name.split(".", 1)
        return schema, table
    return None, name


def _normalize_type(raw: str) -> str:
    collapsed = re.sub(r"\s+", " ", raw.strip().upper())
    # Preserve precision args: VARCHAR(64) etc.
    base = collapsed.split("(", 1)[0].strip()
    suffix = collapsed[len(base) :]
    mapped = _TYPE_ALIASES.get(base, base)
    return f"{mapped}{suffix}"


def _parse_columns(body: str) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for part in _split_column_parts(body):
        line = part.strip()
        if not line:
            continue
        upper = line.upper()
        if any(upper.startswith(prefix) for prefix in _CONSTRAINT_PREFIXES):
            continue
        match = _COLUMN.match(line)
        if match is None:
            continue
        columns.append(
            {
                "name": match.group("name").strip().strip('"'),
                "type": _normalize_type(match.group("type")),
            }
        )
    return columns


def _split_column_parts(body: str) -> list[str]:
    """Split column list on top-level commas (ignore commas inside parentheses)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in body:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts
