"""Assurance case model and HTML/JSON report writers (§20 sections).

Reports are assembled from canonical artifacts only. Build success is not
fidelity evidence.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash
from envassure.ir.models import AmbiguityRecord, WorldDefinition

# Spec §20 outline — HTML and JSON expose these section ids stably.
ASSURANCE_CASE_SECTIONS: tuple[tuple[str, str], ...] = (
    ("20.1", "Identity and scope"),
    ("20.2", "Assumptions and unsupported semantics"),
    ("20.3", "Fidelity profile"),
    ("20.4", "Claims and evidence"),
    ("20.5", "Static analysis evidence"),
    ("20.6", "Dynamic validation evidence"),
    ("20.7", "Differential validation evidence"),
    ("20.8", "Ambiguities and residual risk"),
    ("20.9", "Evidence obligations"),
    ("20.10", "Provenance and artifact digests"),
    ("20.11", "Diagnostics summary"),
    ("20.12", "Release readiness"),
)


class FidelityDimensionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    level: str
    evidence_refs: list[str] = Field(default_factory=list)
    notes: str | None = None


class AssuranceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    status: str
    evidence_refs: list[str] = Field(default_factory=list)
    residual_risk: str | None = None


class AssuranceSection(BaseModel):
    """One §20 section populated from canonical inputs only."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    body: list[str] = Field(default_factory=list)
    tables: list[dict[str, Any]] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    status: str = "present"


class AssuranceCase(BaseModel):
    """Assurance case assembled only from canonical artifacts."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    environment_id: str
    environment_name: str
    environment_version: str
    ir_digest: str
    generated_at: str
    declared_fidelity_level: str
    fidelity_profile: list[FidelityDimensionEvidence] = Field(default_factory=list)
    claims: list[AssuranceClaim] = Field(default_factory=list)
    sections: list[AssuranceSection] = Field(default_factory=list)
    diagnostics_summary: dict[str, int] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_digest(self) -> str:
        payload = self.model_dump(mode="json")
        # Exclude wall-clock so digests are stable across regenerations of the same inputs.
        payload.pop("generated_at", None)
        return canonical_hash(payload)

    def section(self, section_id: str) -> AssuranceSection | None:
        for item in self.sections:
            if item.id == section_id:
                return item
        return None


def build_assurance_case(
    world: WorldDefinition,
    *,
    diagnostics: list[dict[str, Any]] | None = None,
    artifacts: dict[str, str] | None = None,
    extra_claims: list[AssuranceClaim] | None = None,
    ambiguities: list[AmbiguityRecord] | list[dict[str, Any]] | None = None,
    static_analysis: dict[str, Any] | None = None,
    dynamic_validation: dict[str, Any] | None = None,
    differential: dict[str, Any] | None = None,
    proof_obligations: Any | None = None,
    generated_at: str | None = None,
) -> AssuranceCase:
    """Build an AssuranceCase from IR and optional canonical artifact digests/payloads."""
    ir_digest = canonical_hash(world.content_dict())
    diag_list = diagnostics or []
    summary: dict[str, int] = {}
    for item in diag_list:
        sev = str(item.get("severity", "unknown"))
        summary[sev] = summary.get(sev, 0) + 1

    artifact_map = dict(artifacts or {})
    artifact_map.setdefault("ir", ir_digest)

    fidelity: list[FidelityDimensionEvidence] = [
        FidelityDimensionEvidence(
            dimension="schema",
            level=world.declared_fidelity_level,
            evidence_refs=[f"ir:{ir_digest[:12]}"],
            notes="Declared fidelity is not a composite score.",
        ),
        FidelityDimensionEvidence(
            dimension="determinism",
            level=world.determinism,
            evidence_refs=[f"ir:{ir_digest[:12]}"],
        ),
    ]
    if differential:
        fidelity.append(
            FidelityDimensionEvidence(
                dimension="differential",
                level=str(differential.get("level") or differential.get("status") or "partial"),
                evidence_refs=list(differential.get("evidence_refs") or []),
                notes=differential.get("notes"),
            )
        )

    claims: list[AssuranceClaim] = []
    for verifier in world.verifiers:
        claims.append(
            AssuranceClaim(
                id=f"claim.verifier.{verifier.id}",
                statement=verifier.statement,
                status=verifier.status,
                evidence_refs=list(verifier.required_evidence),
                residual_risk="; ".join(verifier.false_positive_risks) or None,
            )
        )
    if extra_claims:
        claims.extend(extra_claims)

    amb_models = _normalize_ambiguities(ambiguities)
    if proof_obligations is None:
        from envassure.obligations import compile_proof_obligations

        proof_obligations = compile_proof_obligations(world)
    sections = _build_sections(
        world,
        ir_digest=ir_digest,
        fidelity=fidelity,
        claims=claims,
        diagnostics=diag_list,
        summary=summary,
        artifacts=artifact_map,
        ambiguities=amb_models,
        static_analysis=static_analysis or {},
        dynamic_validation=dynamic_validation or {},
        differential=differential or {},
        proof_obligations=proof_obligations,
    )

    open_amb = sum(1 for a in amb_models if a.status == "open")
    release_blocked = open_amb > 0 or any(c.status in {"draft", "candidate"} for c in claims)

    return AssuranceCase(
        environment_id=world.environment_id,
        environment_name=world.name,
        environment_version=world.version,
        ir_digest=ir_digest,
        generated_at=generated_at or datetime.now(UTC).isoformat(),
        declared_fidelity_level=world.declared_fidelity_level,
        fidelity_profile=fidelity,
        claims=claims,
        sections=sections,
        diagnostics_summary=summary,
        artifacts=artifact_map,
        metadata={
            "task_count": len(world.tasks),
            "action_count": len(world.actions),
            "canonical_only": True,
            "section_ids": [s[0] for s in ASSURANCE_CASE_SECTIONS],
            "open_ambiguities": open_amb,
            "release_ready": not release_blocked,
            "proof_obligation_count": len(getattr(proof_obligations, "obligations", []) or []),
            "proof_obligation_disclaimer": getattr(proof_obligations, "disclaimer", None),
        },
    )


def write_assurance_report(
    case: AssuranceCase,
    output_dir: Path,
    *,
    basename: str = "assurance-case",
) -> dict[str, Path]:
    """Write JSON + HTML assurance reports; return paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{basename}.json"
    html_path = output_dir / f"{basename}.html"
    payload = case.model_dump(mode="json")
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    html_path.write_text(render_assurance_html(case), encoding="utf-8")
    return {"json": json_path, "html": html_path}


def assurance_pack_members(case: AssuranceCase) -> dict[str, str]:
    """Return pack-relative path → text for packaging hooks."""
    return {
        "reports/assurance-case.json": json.dumps(case.model_dump(mode="json"), indent=2) + "\n",
        "reports/assurance-case.html": render_assurance_html(case),
    }


def load_assurance_case(path: Path) -> AssuranceCase:
    """Load a previously written assurance-case JSON (canonical artifact)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AssuranceCase.model_validate(data)


def render_assurance_html(case: AssuranceCase) -> str:
    """Render the full §20 HTML report from an AssuranceCase JSON model."""
    toc = "\n".join(
        (f'<li><a href="#sec-{_esc(s.id.replace(".", "-"))}">{_esc(s.id)} {_esc(s.title)}</a></li>')
        for s in case.sections
    )
    body_parts: list[str] = []
    for section in case.sections:
        anchor = section.id.replace(".", "-")
        paragraphs = "\n".join(f"<p>{_esc(p)}</p>" for p in section.body)
        tables_html = ""
        for table in section.tables:
            headers = table.get("headers") or []
            rows = table.get("rows") or []
            head = "".join(f"<th>{_esc(str(h))}</th>" for h in headers)
            row_html = []
            for row in rows:
                cells = "".join(f"<td>{_esc(str(c))}</td>" for c in row)
                row_html.append(f"<tr>{cells}</tr>")
            caption = _esc(str(table.get("caption") or ""))
            tables_html += (
                f"<table><caption>{caption}</caption>"
                f"<thead><tr>{head}</tr></thead>"
                f"<tbody>\n{chr(10).join(row_html)}\n</tbody></table>\n"
            )
        refs = ""
        if section.artifact_refs:
            items = "".join(f"<li><code>{_esc(r)}</code></li>" for r in section.artifact_refs)
            refs = f"<ul class='refs'>{items}</ul>"
        body_parts.append(
            f'<section id="sec-{_esc(anchor)}">\n'
            f"<h2>{_esc(section.id)} {_esc(section.title)}</h2>\n"
            f"{paragraphs}\n{tables_html}{refs}\n"
            f"</section>\n"
        )
    diag = ", ".join(f"{k}={v}" for k, v in sorted(case.diagnostics_summary.items()))
    release = "ready" if case.metadata.get("release_ready") else "blocked"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Assurance Case — {_esc(case.environment_id)}</title>
  <style>
    :root {{
      --ink: #1c1917;
      --muted: #57534e;
      --line: #d6d3d1;
      --band: #f5f5f4;
      --accent: #0f766e;
    }}
    body {{
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(ellipse at top left, #ecfdf5 0%, transparent 45%),
        linear-gradient(180deg, #fafaf9 0%, #f5f5f4 100%);
      line-height: 1.45;
    }}
    header {{
      padding: 2.5rem 2rem 1.5rem;
      border-bottom: 1px solid var(--line);
      background: linear-gradient(135deg, #f0fdfa 0%, #fafaf9 55%);
    }}
    main {{ max-width: 52rem; margin: 0 auto; padding: 1.5rem 1.25rem 3rem; }}
    h1 {{ font-size: 1.85rem; margin: 0 0 0.35rem; letter-spacing: -0.02em; }}
    h2 {{ font-size: 1.25rem; margin-top: 2rem; color: var(--accent); }}
    .meta {{ color: var(--muted); font-size: 0.95rem; }}
    nav.toc {{
      background: var(--band);
      border: 1px solid var(--line);
      padding: 1rem 1.25rem;
      margin: 1.25rem 0 2rem;
    }}
    nav.toc ol {{ margin: 0.4rem 0 0; padding-left: 1.25rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.95rem; }}
    th, td {{ border: 1px solid var(--line); padding: 0.4rem 0.6rem; text-align: left; }}
    th {{ background: var(--band); }}
    caption {{ caption-side: top; text-align: left; font-weight: 600; margin-bottom: 0.35rem; }}
    code {{ font-family: "IBM Plex Mono", Consolas, monospace; font-size: 0.88em; }}
    ul.refs {{ font-size: 0.9rem; color: var(--muted); }}
    footer {{
      margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid var(--line);
      color: var(--muted); font-size: 0.9rem;
    }}
    .badge {{
      display: inline-block; padding: 0.15rem 0.55rem; border: 1px solid var(--line);
      background: #fff; font-size: 0.85rem; letter-spacing: 0.02em;
    }}
  </style>
</head>
<body>
  <header>
    <p class="meta">EnvAssure assurance case · canonical artifacts only</p>
    <h1>{_esc(case.environment_name)}</h1>
    <p class="meta">
      <code>{_esc(case.environment_id)}</code>
      · version {_esc(case.environment_version)}
      · fidelity {_esc(case.declared_fidelity_level)}
      · release <span class="badge">{_esc(release)}</span>
    </p>
    <p class="meta">Generated {_esc(case.generated_at)} · IR digest
      <code>{_esc(case.ir_digest)}</code></p>
    <p class="meta">Diagnostics: {_esc(diag or "none")}</p>
  </header>
  <main>
    <nav class="toc" aria-label="Section outline">
      <strong>§20 sections</strong>
      <ol>
{toc}
      </ol>
    </nav>
{"".join(body_parts)}
    <footer>
      Assembled from canonical artifacts only. Build success is not fidelity evidence.
      Content digest <code>{_esc(case.content_digest())}</code>.
    </footer>
  </main>
</body>
</html>
"""


# Back-compat alias used by older call sites.
_render_html = render_assurance_html


def _normalize_ambiguities(
    ambiguities: list[AmbiguityRecord] | list[dict[str, Any]] | None,
) -> list[AmbiguityRecord]:
    if not ambiguities:
        return []
    out: list[AmbiguityRecord] = []
    for item in ambiguities:
        if isinstance(item, AmbiguityRecord):
            out.append(item)
        else:
            out.append(AmbiguityRecord.model_validate(item))
    return out


def _build_sections(
    world: WorldDefinition,
    *,
    ir_digest: str,
    fidelity: list[FidelityDimensionEvidence],
    claims: list[AssuranceClaim],
    diagnostics: list[dict[str, Any]],
    summary: dict[str, int],
    artifacts: dict[str, str],
    ambiguities: list[AmbiguityRecord],
    static_analysis: dict[str, Any],
    dynamic_validation: dict[str, Any],
    differential: dict[str, Any],
    proof_obligations: Any | None = None,
) -> list[AssuranceSection]:
    unsupported = list(world.known_unsupported_behavior)
    for action in world.actions:
        unsupported.extend(action.unsupported_semantics)
    for rule in world.transitions:
        unsupported.extend(rule.unsupported_assumptions)
    unsupported = list(dict.fromkeys(unsupported))

    open_amb = [a for a in ambiguities if a.status == "open"]
    release_ready = not open_amb and not any(c.status in {"draft", "candidate"} for c in claims)

    by_id: dict[str, AssuranceSection] = {}

    by_id["20.1"] = AssuranceSection(
        id="20.1",
        title="Identity and scope",
        body=[
            f"Environment {world.name} ({world.environment_id}) version {world.version}.",
            f"Domain: {world.domain}. Determinism: {world.determinism}.",
            f"IR version {world.ir_version}; digest {ir_digest}.",
            f"Actions: {len(world.actions)}; actors: {len(world.actors)}; "
            f"tasks: {len(world.tasks)}; verifiers: {len(world.verifiers)}.",
        ],
        artifact_refs=[f"ir:{ir_digest[:16]}"],
    )

    by_id["20.2"] = AssuranceSection(
        id="20.2",
        title="Assumptions and unsupported semantics",
        body=[
            "Unsupported semantics must remain explicit; they are not silently filled.",
            *(
                [f"Declared unsupported: {'; '.join(unsupported)}"]
                if unsupported
                else ["No known_unsupported_behavior or action unsupported_semantics entries."]
            ),
        ],
        tables=[
            {
                "caption": "Unsupported assumptions",
                "headers": ["Item"],
                "rows": [[u] for u in unsupported] or [["(none)"]],
            }
        ],
    )

    by_id["20.3"] = AssuranceSection(
        id="20.3",
        title="Fidelity profile",
        body=[
            "Fidelity is multi-dimensional; declared level is not a composite score.",
            f"Declared fidelity level: {world.declared_fidelity_level}.",
        ],
        tables=[
            {
                "caption": "Fidelity dimensions",
                "headers": ["Dimension", "Level", "Notes"],
                "rows": [[f.dimension, f.level, f.notes or ""] for f in fidelity],
            }
        ],
        artifact_refs=[r for f in fidelity for r in f.evidence_refs],
    )

    by_id["20.4"] = AssuranceSection(
        id="20.4",
        title="Claims and evidence",
        body=[
            f"{len(claims)} claim(s) derived from verifier definitions and extras.",
        ],
        tables=[
            {
                "caption": "Claims",
                "headers": ["Id", "Status", "Statement"],
                "rows": [[c.id, c.status, c.statement] for c in claims] or [["—", "—", "(none)"]],
            }
        ],
    )

    by_id["20.5"] = AssuranceSection(
        id="20.5",
        title="Static analysis evidence",
        body=_section_body_from_artifact(
            static_analysis,
            empty="No static analysis artifact supplied; section records absence.",
        ),
        artifact_refs=list(static_analysis.get("evidence_refs") or []),
        status="present" if static_analysis else "absent",
        tables=_maybe_finding_table(static_analysis, "Static findings"),
    )

    by_id["20.6"] = AssuranceSection(
        id="20.6",
        title="Dynamic validation evidence",
        body=_section_body_from_artifact(
            dynamic_validation,
            empty="No dynamic validation artifact supplied; section records absence.",
        ),
        artifact_refs=list(dynamic_validation.get("evidence_refs") or []),
        status="present" if dynamic_validation else "absent",
        tables=_maybe_finding_table(dynamic_validation, "Dynamic findings"),
    )

    by_id["20.7"] = AssuranceSection(
        id="20.7",
        title="Differential validation evidence",
        body=_section_body_from_artifact(
            differential,
            empty="No differential validation artifact supplied; section records absence.",
        ),
        artifact_refs=list(differential.get("evidence_refs") or []),
        status="present" if differential else "absent",
        tables=_maybe_finding_table(differential, "Differential summary"),
    )

    by_id["20.8"] = AssuranceSection(
        id="20.8",
        title="Ambiguities and residual risk",
        body=[
            f"{len(ambiguities)} ambiguity record(s); {len(open_amb)} open.",
            "Open ambiguities block release-grade packs.",
        ],
        tables=[
            {
                "caption": "Ambiguities",
                "headers": ["Id", "Status", "Class", "Subject"],
                "rows": [[a.id, a.status, a.conflict_class, a.subject] for a in ambiguities]
                or [["—", "—", "—", "(none)"]],
            }
        ],
    )

    by_id["20.9"] = AssuranceSection(
        id="20.9",
        title="Evidence obligations",
        body=[
            f"{len(world.evidence_obligations)} evidence obligation(s) declared on the world.",
            (
                f"{len(getattr(proof_obligations, 'obligations', []) or [])} compiled "
                "proof obligation(s). Mechanism strength is recorded explicitly; "
                "compiled obligations are not formal proofs."
            ),
            getattr(
                proof_obligations,
                "disclaimer",
                "Proof obligations declare expected evidence — not completed proofs.",
            ),
        ],
        tables=[
            {
                "caption": "Evidence obligations (IR)",
                "headers": ["Id", "Class", "Trigger", "Failure behavior"],
                "rows": [
                    [o.id, o.evidence_class, o.trigger, o.failure_behavior]
                    for o in world.evidence_obligations
                ]
                or [["—", "—", "—", "(none)"]],
            },
            {
                "caption": "Compiled proof obligations",
                "headers": ["Id", "Kind", "Status", "Strength"],
                "rows": [
                    [o.id, o.claim_kind, o.status, o.mechanism_strength]
                    for o in (getattr(proof_obligations, "obligations", None) or [])
                ]
                or [["—", "—", "—", "(none)"]],
            },
        ],
    )

    by_id["20.10"] = AssuranceSection(
        id="20.10",
        title="Provenance and artifact digests",
        body=[
            "All digests below are over canonical JSON encodings.",
        ],
        tables=[
            {
                "caption": "Artifact digests",
                "headers": ["Artifact", "Digest"],
                "rows": [[k, v] for k, v in sorted(artifacts.items())] or [["ir", ir_digest]],
            }
        ],
        artifact_refs=[f"{k}:{v[:16]}" for k, v in sorted(artifacts.items())],
    )

    by_id["20.11"] = AssuranceSection(
        id="20.11",
        title="Diagnostics summary",
        body=[
            "Severity counts from supplied diagnostic artifacts only.",
            *(
                [", ".join(f"{k}={v}" for k, v in sorted(summary.items()))]
                if summary
                else ["No diagnostics supplied."]
            ),
        ],
        tables=[
            {
                "caption": "Diagnostics",
                "headers": ["Code", "Severity", "Summary"],
                "rows": [
                    [
                        str(d.get("code", "")),
                        str(d.get("severity", "")),
                        str(d.get("summary", d.get("message", ""))),
                    ]
                    for d in diagnostics[:50]
                ]
                or [["—", "—", "(none)"]],
            }
        ],
    )

    by_id["20.12"] = AssuranceSection(
        id="20.12",
        title="Release readiness",
        body=[
            "Release readiness requires no open blocking ambiguities and non-draft claims.",
            f"Status: {'READY' if release_ready else 'BLOCKED'}.",
            f"Open ambiguities: {len(open_amb)}.",
        ],
        status="ready" if release_ready else "blocked",
    )

    return [by_id[sid] for sid, _title in ASSURANCE_CASE_SECTIONS]


def _section_body_from_artifact(payload: dict[str, Any], *, empty: str) -> list[str]:
    if not payload:
        return [empty]
    body: list[str] = []
    if payload.get("summary"):
        body.append(str(payload["summary"]))
    if payload.get("status"):
        body.append(f"Status: {payload['status']}")
    if payload.get("notes"):
        body.append(str(payload["notes"]))
    if not body:
        body.append("Artifact present; see tables and refs.")
    return body


def _maybe_finding_table(payload: dict[str, Any], caption: str) -> list[dict[str, Any]]:
    findings = payload.get("findings") or payload.get("rows")
    if not findings:
        if payload.get("metrics"):
            metrics = payload["metrics"]
            if isinstance(metrics, dict):
                return [
                    {
                        "caption": caption,
                        "headers": ["Metric", "Value"],
                        "rows": [[str(k), str(v)] for k, v in sorted(metrics.items())],
                    }
                ]
        return []
    if findings and isinstance(findings[0], dict):
        headers = list(findings[0].keys())
        rows = [[str(row.get(h, "")) for h in headers] for row in findings]
        return [{"caption": caption, "headers": headers, "rows": rows}]
    return [{"caption": caption, "headers": ["Finding"], "rows": [[str(f)] for f in findings]}]


def _esc(value: str) -> str:
    return (
        value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )
