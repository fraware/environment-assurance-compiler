"""OpenAPI YAML/JSON adapter → action, schema, and auth hint facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import SourceParseError

_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


class OpenAPIAdapter:
    """Extract candidate facts from OpenAPI 3.x documents."""

    kind = "openapi"

    def parse(self, path: Path) -> list[SemanticFact]:
        data = _load_openapi(path)
        source = str(path)
        facts: list[SemanticFact] = []
        confidence = ConfidenceRecord(
            evidence_class="api_contract",
            extractor_certainty="high",
        )

        paths = data.get("paths") or {}
        if not isinstance(paths, dict):
            raise SourceParseError(path, "paths must be a mapping")

        for route, item in paths.items():
            if not isinstance(item, dict):
                continue
            for method, op in item.items():
                if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                    continue
                action_id = _operation_id(op, method, route)
                subject = EntityRef(kind="action", id=action_id)
                facts.extend(
                    _action_facts(
                        subject=subject,
                        method=method.upper(),
                        route=str(route),
                        op=op,
                        source=source,
                        confidence=confidence,
                    )
                )

        schemas = ((data.get("components") or {}).get("schemas")) or {}
        if isinstance(schemas, dict):
            for name, schema in schemas.items():
                subject = EntityRef(kind="schema", id=str(name))
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="schema",
                            subject_id=str(name),
                            predicate="schema_definition",
                            source=source,
                        ),
                        subject=subject,
                        predicate="schema_definition",
                        value=schema if isinstance(schema, dict) else {"raw": schema},
                        source_refs=[source],
                        extraction_method="openapi.components.schemas",
                        confidence=confidence,
                        kind_tags=["schema"],
                    )
                )

        security = ((data.get("components") or {}).get("securitySchemes")) or {}
        if isinstance(security, dict):
            for name, scheme in security.items():
                subject = EntityRef(kind="auth", id=str(name))
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="auth",
                            subject_id=str(name),
                            predicate="auth_scheme",
                            source=source,
                        ),
                        subject=subject,
                        predicate="auth_scheme",
                        value=scheme if isinstance(scheme, dict) else {"raw": scheme},
                        source_refs=[source],
                        extraction_method="openapi.components.securitySchemes",
                        confidence=confidence,
                        kind_tags=["auth", "auth_hint"],
                    )
                )

        if not facts:
            raise SourceParseError(path, "no operations, schemas, or security schemes found")
        return facts


def _load_openapi(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SourceParseError(path, "file not found")
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    try:
        data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SourceParseError(path, f"invalid document: {exc}") from exc
    if not isinstance(data, dict):
        raise SourceParseError(path, "document root must be a mapping")
    if "openapi" not in data and "swagger" not in data and "paths" not in data:
        raise SourceParseError(path, "not an OpenAPI document (missing openapi/swagger/paths)")
    return data


def _operation_id(op: dict[str, Any], method: str, route: str) -> str:
    if isinstance(op.get("operationId"), str) and op["operationId"].strip():
        return op["operationId"].strip()
    cleaned = route.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method.lower()}_{cleaned or 'root'}"


def _action_facts(
    *,
    subject: EntityRef,
    method: str,
    route: str,
    op: dict[str, Any],
    source: str,
    confidence: ConfidenceRecord,
) -> list[SemanticFact]:
    facts: list[SemanticFact] = [
        SemanticFact(
            fact_id=make_fact_id(
                subject_kind=subject.kind,
                subject_id=subject.id,
                predicate="is_action",
                source=source,
            ),
            subject=subject,
            predicate="is_action",
            value=True,
            source_refs=[source],
            extraction_method="openapi.paths.operation",
            confidence=confidence,
            kind_tags=["action"],
        ),
        SemanticFact(
            fact_id=make_fact_id(
                subject_kind=subject.kind,
                subject_id=subject.id,
                predicate="http_method",
                source=source,
            ),
            subject=subject,
            predicate="http_method",
            value=method,
            source_refs=[source],
            extraction_method="openapi.paths.operation",
            confidence=confidence,
            kind_tags=["action"],
        ),
        SemanticFact(
            fact_id=make_fact_id(
                subject_kind=subject.kind,
                subject_id=subject.id,
                predicate="http_path",
                source=source,
            ),
            subject=subject,
            predicate="http_path",
            value=route,
            source_refs=[source],
            extraction_method="openapi.paths.operation",
            confidence=confidence,
            kind_tags=["action"],
        ),
    ]

    summary = op.get("summary") or op.get("description")
    if isinstance(summary, str) and summary.strip():
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=subject.kind,
                    subject_id=subject.id,
                    predicate="description",
                    source=source,
                ),
                subject=subject,
                predicate="description",
                value=summary.strip(),
                source_refs=[source],
                extraction_method="openapi.paths.operation",
                confidence=confidence,
                kind_tags=["action"],
            )
        )

    responses = op.get("responses") or {}
    if isinstance(responses, dict):
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=subject.kind,
                    subject_id=subject.id,
                    predicate="http_responses",
                    source=source,
                ),
                subject=subject,
                predicate="http_responses",
                value=sorted(str(k) for k in responses),
                source_refs=[source],
                extraction_method="openapi.paths.operation.responses",
                confidence=confidence,
                kind_tags=["action"],
            )
        )
        # Timeout / gateway errors without state semantics.
        if "504" in responses or 504 in responses:
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind=subject.kind,
                        subject_id=subject.id,
                        predicate="timeout_behavior",
                        source=source,
                    ),
                    subject=subject,
                    predicate="timeout_behavior",
                    value="http_504_no_state_semantics",
                    source_refs=[source],
                    extraction_method="openapi.paths.operation.responses",
                    confidence=ConfidenceRecord(
                        evidence_class="api_contract",
                        extractor_certainty="medium",
                    ),
                    kind_tags=["action", "timeout"],
                )
            )

    security = op.get("security")
    if security is not None:
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=subject.kind,
                    subject_id=subject.id,
                    predicate="auth_hint",
                    source=source,
                ),
                subject=subject,
                predicate="auth_hint",
                value=security,
                source_refs=[source],
                extraction_method="openapi.paths.operation.security",
                confidence=confidence,
                kind_tags=["action", "auth_hint"],
            )
        )

    # Explicit extension fields if present.
    for pred in ("timeout_behavior", "retry_behavior", "idempotency"):
        if pred in op and op[pred] is not None:
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind=subject.kind,
                        subject_id=subject.id,
                        predicate=pred,
                        source=source,
                    ),
                    subject=subject,
                    predicate=pred,
                    value=op[pred],
                    source_refs=[source],
                    extraction_method="openapi.extension",
                    confidence=confidence,
                    kind_tags=["action", pred],
                )
            )

    return facts
