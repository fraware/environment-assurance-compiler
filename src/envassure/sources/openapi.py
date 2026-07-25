"""OpenAPI YAML/JSON adapter → action, schema, and auth hint facts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import ConfidenceRecord, DerivationClass, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import AdapterResult, SourceParseError

_HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})

# Constructs outside the OpenAPI adapter supported matrix (0.2).
_UNSUPPORTED_ROOT_KEYS = frozenset({"webhooks", "x-webhooks"})
_UNSUPPORTED_OPERATION_KEYS = frozenset(
    {"callbacks", "links", "servers", "externalDocs", "x-amazon-apigateway-integration"}
)


def _direct_conf(*, certainty: str = "high", notes: str | None = None) -> ConfidenceRecord:
    return ConfidenceRecord(
        evidence_class="api_contract",
        derivation_class="direct",
        extractor_certainty=certainty,  # type: ignore[arg-type]
        notes=notes,
    )


def _inferred_conf(*, certainty: str = "medium", notes: str | None = None) -> ConfidenceRecord:
    return ConfidenceRecord(
        evidence_class="api_contract",
        derivation_class="inferred",
        extractor_certainty=certainty,  # type: ignore[arg-type]
        notes=notes,
    )


class OpenAPIAdapter:
    """Extract candidate facts from OpenAPI 3.x documents.

    Supported matrix (0.2): local ``$ref`` resolution under ``#/components``,
    path-level parameter inheritance, request/response content media types,
    operation and global security, components schemas/securitySchemes.
    Unsupported constructs emit ``EAC1006`` and are not projected as
    authoritative semantics. Confidence is never uniform: direct excerpts use
    high/medium certainty; inferred semantics (e.g. 504 → timeout hint) use
    medium/low with ``derivation_class=inferred``.
    """

    kind = "openapi"

    def parse(self, path: Path) -> list[SemanticFact]:
        return self.parse_detailed(path).facts

    def parse_detailed(self, path: Path) -> AdapterResult:
        data = _load_openapi(path)
        source = str(path)
        report = DiagnosticReport()
        facts: list[SemanticFact] = []
        resolver = _RefResolver(data, source=source, diagnostics=report)

        for feature in sorted(_UNSUPPORTED_ROOT_KEYS & set(data)):
            report.add(
                make_diagnostic(
                    "EAC1006",
                    feature=feature,
                    subject=source,
                    reason="root-level construct is outside the OpenAPI adapter matrix",
                )
            )

        global_security = data.get("security")
        paths = data.get("paths") or {}
        if not isinstance(paths, dict):
            raise SourceParseError(path, "paths must be a mapping")

        for route, item in paths.items():
            if not isinstance(item, dict):
                continue
            path_item = resolver.resolve_value(item, path=f"paths.{route}")
            if not isinstance(path_item, dict):
                continue
            path_params = (
                path_item.get("parameters") if isinstance(path_item.get("parameters"), list) else []
            )
            for method, op in path_item.items():
                if method.lower() not in _HTTP_METHODS or not isinstance(op, dict):
                    continue
                resolved_op = resolver.resolve_value(op, path=f"paths.{route}.{method}")
                if not isinstance(resolved_op, dict):
                    continue
                action_id = _operation_id(resolved_op, method, route)
                subject = EntityRef(kind="action", id=action_id)
                for feature in sorted(_UNSUPPORTED_OPERATION_KEYS & set(resolved_op)):
                    report.add(
                        make_diagnostic(
                            "EAC1006",
                            feature=feature,
                            subject=f"action:{action_id}",
                            reason=f"operation {method.upper()} {route} uses unsupported construct",
                        )
                    )
                facts.extend(
                    _action_facts(
                        subject=subject,
                        method=method.upper(),
                        route=str(route),
                        op=resolved_op,
                        path_params=path_params if isinstance(path_params, list) else [],
                        global_security=global_security,
                        source=source,
                        resolver=resolver,
                    )
                )

        schemas = ((data.get("components") or {}).get("schemas")) or {}
        if isinstance(schemas, dict):
            for name, schema in schemas.items():
                subject = EntityRef(kind="schema", id=str(name))
                resolved = resolver.resolve_value(schema, path=f"components.schemas.{name}")
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
                        value=resolved if isinstance(resolved, dict) else {"raw": resolved},
                        source_refs=[source],
                        extraction_method="openapi.components.schemas",
                        confidence=_direct_conf(certainty="high"),
                        kind_tags=["schema"],
                    )
                )

        security = ((data.get("components") or {}).get("securitySchemes")) or {}
        if isinstance(security, dict):
            for name, scheme in security.items():
                subject = EntityRef(kind="auth", id=str(name))
                resolved = resolver.resolve_value(scheme, path=f"components.securitySchemes.{name}")
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
                        value=resolved if isinstance(resolved, dict) else {"raw": resolved},
                        source_refs=[source],
                        extraction_method="openapi.components.securitySchemes",
                        confidence=_direct_conf(certainty="high"),
                        kind_tags=["auth", "auth_hint"],
                    )
                )

        if not facts:
            raise SourceParseError(path, "no operations, schemas, or security schemes found")
        return AdapterResult(facts=facts, diagnostics=report)


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


class _RefResolver:
    """Resolve local OpenAPI ``$ref`` pointers under the document root."""

    def __init__(
        self,
        root: dict[str, Any],
        *,
        source: str,
        diagnostics: DiagnosticReport,
    ) -> None:
        self._root = root
        self._source = source
        self._diagnostics = diagnostics
        self._stack: set[str] = set()

    def resolve_value(self, value: Any, *, path: str, depth: int = 0) -> Any:
        if depth > 32:
            self._diagnostics.add(
                make_diagnostic(
                    "EAC1006",
                    feature="$ref",
                    subject=path,
                    reason="reference resolution depth exceeded",
                )
            )
            return value
        if isinstance(value, dict) and "$ref" in value:
            ref = value["$ref"]
            if not isinstance(ref, str):
                return value
            resolved = self._resolve_ref(ref, path=path)
            if resolved is None:
                return value
            # Merge sibling keys (OpenAPI 3.1 style) over the target.
            if isinstance(resolved, dict):
                merged = {**resolved, **{k: v for k, v in value.items() if k != "$ref"}}
                return self.resolve_value(merged, path=path, depth=depth + 1)
            return resolved
        if isinstance(value, dict):
            return {
                key: self.resolve_value(item, path=f"{path}.{key}", depth=depth + 1)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                self.resolve_value(item, path=f"{path}[{index}]", depth=depth + 1)
                for index, item in enumerate(value)
            ]
        return value

    def _resolve_ref(self, ref: str, *, path: str) -> Any | None:
        if not ref.startswith("#/"):
            self._diagnostics.add(
                make_diagnostic(
                    "EAC1006",
                    feature="$ref",
                    subject=path,
                    reason=f"remote or non-local ref not supported: {ref}",
                )
            )
            return None
        if ref in self._stack:
            self._diagnostics.add(
                make_diagnostic(
                    "EAC1006",
                    feature="$ref",
                    subject=path,
                    reason=f"circular $ref detected: {ref}",
                )
            )
            return None
        parts = ref[2:].split("/")
        node: Any = self._root
        self._stack.add(ref)
        try:
            for part in parts:
                key = part.replace("~1", "/").replace("~0", "~")
                if not isinstance(node, dict) or key not in node:
                    self._diagnostics.add(
                        make_diagnostic(
                            "EAC1006",
                            feature="$ref",
                            subject=path,
                            reason=f"unresolved local ref: {ref}",
                        )
                    )
                    return None
                node = node[key]
            return node
        finally:
            self._stack.discard(ref)


def _merge_parameters(
    path_params: list[Any],
    op_params: list[Any],
    *,
    resolver: _RefResolver,
    subject: str,
) -> list[dict[str, Any]]:
    """Merge path-level and operation parameters; operation wins on (name, in)."""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in [*path_params, *op_params]:
        resolved = resolver.resolve_value(raw, path=f"{subject}.parameters")
        if not isinstance(resolved, dict):
            continue
        name = resolved.get("name")
        location = resolved.get("in")
        if not isinstance(name, str) or not isinstance(location, str):
            continue
        merged[(name, location)] = resolved
    return list(merged.values())


def _content_media_types(content: Any) -> list[str]:
    if not isinstance(content, dict):
        return []
    return sorted(str(k) for k in content)


def _action_facts(
    *,
    subject: EntityRef,
    method: str,
    route: str,
    op: dict[str, Any],
    path_params: list[Any],
    global_security: Any,
    source: str,
    resolver: _RefResolver,
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
            confidence=_direct_conf(certainty="high"),
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
            confidence=_direct_conf(certainty="high"),
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
            confidence=_direct_conf(certainty="high"),
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
                confidence=_direct_conf(certainty="medium"),
                kind_tags=["action"],
            )
        )

    params = _merge_parameters(
        path_params,
        op.get("parameters") if isinstance(op.get("parameters"), list) else [],
        resolver=resolver,
        subject=f"action:{subject.id}",
    )
    if params:
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=subject.kind,
                    subject_id=subject.id,
                    predicate="http_parameters",
                    source=source,
                ),
                subject=subject,
                predicate="http_parameters",
                value=[
                    {
                        "name": p.get("name"),
                        "in": p.get("in"),
                        "required": bool(p.get("required", False)),
                        "schema": p.get("schema"),
                    }
                    for p in params
                ],
                source_refs=[source],
                extraction_method="openapi.paths.operation.parameters",
                confidence=_direct_conf(certainty="high"),
                kind_tags=["action", "parameters"],
            )
        )

    request_body = op.get("requestBody")
    if request_body is not None:
        resolved_body = resolver.resolve_value(
            request_body, path=f"action:{subject.id}.requestBody"
        )
        content = resolved_body.get("content") if isinstance(resolved_body, dict) else None
        media_types = _content_media_types(content)
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=subject.kind,
                    subject_id=subject.id,
                    predicate="http_request_content",
                    source=source,
                ),
                subject=subject,
                predicate="http_request_content",
                value={
                    "required": bool(
                        isinstance(resolved_body, dict) and resolved_body.get("required")
                    ),
                    "media_types": media_types,
                },
                source_refs=[source],
                extraction_method="openapi.paths.operation.requestBody",
                confidence=_direct_conf(certainty="high"),
                kind_tags=["action", "request"],
            )
        )

    responses = op.get("responses") or {}
    if isinstance(responses, dict):
        response_summary: dict[str, Any] = {}
        for code, resp in responses.items():
            resolved_resp = resolver.resolve_value(
                resp, path=f"action:{subject.id}.responses.{code}"
            )
            content = resolved_resp.get("content") if isinstance(resolved_resp, dict) else None
            response_summary[str(code)] = {
                "media_types": _content_media_types(content),
                "description": (
                    resolved_resp.get("description") if isinstance(resolved_resp, dict) else None
                ),
            }
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
                value=sorted(response_summary),
                source_refs=[source],
                extraction_method="openapi.paths.operation.responses",
                confidence=_direct_conf(certainty="high"),
                kind_tags=["action"],
            )
        )
        facts.append(
            SemanticFact(
                fact_id=make_fact_id(
                    subject_kind=subject.kind,
                    subject_id=subject.id,
                    predicate="http_response_content",
                    source=source,
                ),
                subject=subject,
                predicate="http_response_content",
                value=response_summary,
                source_refs=[source],
                extraction_method="openapi.paths.operation.responses.content",
                confidence=_direct_conf(certainty="medium"),
                kind_tags=["action", "response"],
            )
        )
        # Timeout / gateway errors without state semantics — inferred, not direct.
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
                    confidence=_inferred_conf(
                        certainty="medium",
                        notes="Inferred from HTTP 504 response presence; contract lacks state semantics.",
                    ),
                    kind_tags=["action", "timeout"],
                )
            )

    # Operation security overrides document-level security; empty list = optional.
    if "security" in op:
        security = op.get("security")
        derivation: DerivationClass = "direct"
        certainty = "high"
        extraction = "openapi.paths.operation.security"
        auth_notes = None
    elif global_security is not None:
        security = global_security
        derivation = "direct"
        certainty = "medium"
        extraction = "openapi.global.security"
        auth_notes = "Inherited from document-level security requirements."
    else:
        security = None
        derivation = "direct"
        certainty = "high"
        extraction = "openapi.paths.operation.security"
        auth_notes = None

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
                extraction_method=extraction,
                confidence=ConfidenceRecord(
                    evidence_class="api_contract",
                    derivation_class=derivation,
                    extractor_certainty=certainty,  # type: ignore[arg-type]
                    notes=auth_notes,
                ),
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
                    confidence=_direct_conf(certainty="medium"),
                    kind_tags=["action", pred],
                )
            )

    return facts
