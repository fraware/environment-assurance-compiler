"""Human-readable diagnostic rendering."""

from __future__ import annotations

from envassure.diagnostics.models import Diagnostic, DiagnosticReport, Severity


def format_diagnostic(diagnostic: Diagnostic) -> str:
    lines: list[str] = [
        f"{diagnostic.code} {diagnostic.severity.value}: {diagnostic.summary}",
    ]
    if diagnostic.subject:
        lines.append(f"  subject: {diagnostic.subject}")
    for ref in diagnostic.source_refs:
        loc = ref.path
        if ref.line is not None:
            loc = f"{loc}:{ref.line}"
            if ref.column is not None:
                loc = f"{loc}:{ref.column}"
        lines.append(f"  source: {loc}")
        if ref.excerpt:
            lines.append(f"    {ref.excerpt}")
    if diagnostic.affected_artifacts:
        lines.append("  affected:")
        for artifact in diagnostic.affected_artifacts:
            lines.append(f"    {artifact}")
    if diagnostic.consequence:
        lines.append(f"  consequence: {diagnostic.consequence}")
    if diagnostic.claim_impact:
        lines.append(f"  claim_impact: {diagnostic.claim_impact}")
    if diagnostic.suggested_repair:
        lines.append(f"  repair: {diagnostic.suggested_repair}")
    return "\n".join(lines)


def format_report(report: DiagnosticReport) -> str:
    if not report.diagnostics:
        return "No diagnostics."
    order = {
        Severity.ERROR: 0,
        Severity.WARNING: 1,
        Severity.NOTE: 2,
        Severity.HELP: 3,
    }
    sorted_diags = sorted(
        report.diagnostics,
        key=lambda d: (order[d.severity], d.code, d.summary),
    )
    return "\n\n".join(format_diagnostic(d) for d in sorted_diags)
