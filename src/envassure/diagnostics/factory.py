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
    claim_impact: str | None = None,
    details: dict[str, Any] | None = None,
    **template_fields: Any,
) -> Diagnostic:
    """Build a Diagnostic from the catalog, formatting the summary template."""
    require_documented(code)
    definition = get_definition(code)
    format_fields = dict(template_fields)
    if subject is not None:
        format_fields.setdefault("subject", subject)

    rendered_summary = summary
    if rendered_summary is None:
        try:
            rendered_summary = definition.summary_template.format(**format_fields)
        except KeyError as exc:
            raise ValueError(f"Missing template field {exc!s} for diagnostic {code}") from exc

    rendered_claim_impact = claim_impact
    if rendered_claim_impact is None and definition.claim_impact_template is not None:
        try:
            rendered_claim_impact = definition.claim_impact_template.format(**format_fields)
        except KeyError:
            # Optional claim impact must not block diagnostic emission.
            rendered_claim_impact = definition.claim_impact_template

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
        claim_impact=rendered_claim_impact,
        details=details or {},
    )
