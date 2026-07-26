"""Structured policy YAML adapter → permission facts."""

from __future__ import annotations

from pathlib import Path

import yaml

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.primitives import EntityRef
from envassure.sources.base import AdapterResult, SourceParseError

_UNSUPPORTED_ROOT_KEYS = frozenset(
    {"rego", "rego_module", "opa", "unsupported_engine", "cedar", "abac_rules"}
)


class PolicyAdapter:
    """Parse structured policy documents into permission facts."""

    kind = "policy"

    def parse(self, path: Path) -> list[SemanticFact]:
        return self.parse_detailed(path).facts

    def parse_detailed(self, path: Path) -> AdapterResult:
        if not path.is_file():
            raise SourceParseError(path, "file not found")
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise SourceParseError(path, f"invalid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise SourceParseError(path, "policy root must be a mapping")

        report = DiagnosticReport()
        source = str(path)
        for feature in sorted(_UNSUPPORTED_ROOT_KEYS & set(data)):
            report.add(
                make_diagnostic(
                    "EAC1006",
                    feature=feature,
                    subject=source,
                    reason="root-level construct is outside the policy adapter matrix",
                )
            )

        permissions = data.get("permissions")
        if permissions is None:
            raise SourceParseError(path, "missing permissions list")
        if not isinstance(permissions, list):
            raise SourceParseError(path, "permissions must be a list")

        confidence = ConfidenceRecord(
            evidence_class="formal_policy",
            derivation_class="direct",
            extractor_certainty="high",
        )
        facts: list[SemanticFact] = []
        for index, entry in enumerate(permissions):
            if not isinstance(entry, dict):
                raise SourceParseError(path, f"permissions[{index}] must be a mapping")
            for feature in sorted({"rego_module", "cedar", "opa"} & set(entry)):
                report.add(
                    make_diagnostic(
                        "EAC1006",
                        feature=feature,
                        subject=f"permissions[{index}]",
                        reason="permission entry uses unsupported policy extension",
                    )
                )
            role = entry.get("role")
            action = entry.get("action")
            effect = entry.get("effect", "allow")
            if not isinstance(role, str) or not role.strip():
                raise SourceParseError(path, f"permissions[{index}] missing role")
            if not isinstance(action, str) or not action.strip():
                raise SourceParseError(path, f"permissions[{index}] missing action")
            if effect not in {"allow", "deny"}:
                raise SourceParseError(path, f"permissions[{index}] effect must be allow|deny")
            perm_id = f"{role.strip()}:{action.strip()}"
            subject = EntityRef(kind="permission", id=perm_id)
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="permission",
                        subject_id=perm_id,
                        predicate="permission_effect",
                        source=source,
                        suffix=str(index),
                    ),
                    subject=subject,
                    predicate="permission_effect",
                    value={
                        "role": role.strip(),
                        "action": action.strip(),
                        "effect": effect,
                        "resource": entry.get("resource"),
                        "condition": entry.get("condition"),
                    },
                    source_refs=[source],
                    extraction_method="policy.permissions",
                    confidence=confidence,
                    kind_tags=["permission", "policy"],
                )
            )
            action_subject = EntityRef(kind="action", id=action.strip())
            facts.append(
                SemanticFact(
                    fact_id=make_fact_id(
                        subject_kind="action",
                        subject_id=action.strip(),
                        predicate="authorization",
                        source=source,
                        suffix=f"{role.strip()}:{effect}",
                    ),
                    subject=action_subject,
                    predicate="authorization",
                    value=f"role:{role.strip()}:{effect}",
                    source_refs=[source],
                    extraction_method="policy.permissions",
                    confidence=confidence,
                    kind_tags=["action", "permission"],
                )
            )

        roles = data.get("roles")
        if isinstance(roles, list):
            for role in roles:
                if not isinstance(role, str):
                    continue
                subject = EntityRef(kind="role", id=role)
                facts.append(
                    SemanticFact(
                        fact_id=make_fact_id(
                            subject_kind="role",
                            subject_id=role,
                            predicate="is_role",
                            source=source,
                        ),
                        subject=subject,
                        predicate="is_role",
                        value=True,
                        source_refs=[source],
                        extraction_method="policy.roles",
                        confidence=confidence,
                        kind_tags=["role", "policy"],
                    )
                )
        return AdapterResult(facts=facts, diagnostics=report)
