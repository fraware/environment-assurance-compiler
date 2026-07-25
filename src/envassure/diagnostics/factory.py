"""Helpers to construct catalogued diagnostics."""

from __future__ import annotations

from typing import Any

from envassure.diagnostics.catalog import get_definition, require_documented
from envassure.diagnostics.models import Diagnostic, Severity, SourceRef


def make_diagnostic(
    code: str,
    *,
    summary: str | None = None,
    severity: Severity | None = None,
    subject: str | None = None,
    source_refs: list[SourceRef] | None = None,
    affected_artifacts: list[str] | None = None,
    consequence: str | None = None,
    suggested_repair: str | None = None,
    details: dict[str, Any] | None = None,
    **template_fields: Any,
) -> Diagnostic:
    """Build a Diagnostic from the catalog, formatting the summary template."""
    require_documented(code)
    definition = get_definition(code)
    rendered_summary = summary
    if rendered_summary is None:
        format_fields = dict(template_fields)
        if subject is not None:
            format_fields.setdefault("subject", subject)
        try:
            rendered_summary = definition.summary_template.format(**format_fields)
        except KeyError as exc:
            raise ValueError(f"Missing template field {exc!s} for diagnostic {code}") from exc
    return Diagnostic(
        code=code,
        severity=severity or definition.severity,
        summary=rendered_summary,
        subject=subject,
        source_refs=source_refs or [],
        affected_artifacts=affected_artifacts or [],
        consequence=consequence if consequence is not None else definition.consequence,
        suggested_repair=(
            suggested_repair if suggested_repair is not None else definition.suggested_repair
        ),
        details=details or {},
    )
