"""Semantic IR diff and advisory semver rationale."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.ir.models import WorldDefinition


class DiffCategory(StrEnum):
    SOURCE_ONLY = "source_only"
    STATE_SCHEMA = "state_schema"
    OBSERVATION = "observation"
    BEHAVIOR = "behavior"
    PERMISSION = "permission"
    FAILURE_SEMANTIC = "failure_semantic"
    VERIFIER = "verifier"
    TASK = "task"
    EVIDENCE_ONLY = "evidence_only"
    META = "meta"


class DiffEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: DiffCategory
    path: str
    change: str
    before: Any = None
    after: Any = None


class DiffResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[DiffEntry] = Field(default_factory=list)
    advisory_semver: str = "none"
    advisory_rationale: str = ""

    @property
    def empty(self) -> bool:
        return not self.entries


def diff_worlds(before: WorldDefinition, after: WorldDefinition) -> DiffResult:
    entries: list[DiffEntry] = []

    if before.semantic_sources != after.semantic_sources:
        entries.append(
            DiffEntry(
                category=DiffCategory.SOURCE_ONLY,
                path="semantic_sources",
                change="modified",
                before=before.semantic_sources,
                after=after.semantic_sources,
            )
        )

    _diff_by_id(
        entries,
        DiffCategory.STATE_SCHEMA,
        "state",
        {s.id: s.model_dump(mode="json") for s in before.state},
        {s.id: s.model_dump(mode="json") for s in after.state},
    )
    _diff_by_id(
        entries,
        DiffCategory.OBSERVATION,
        "observations",
        {o.id: o.model_dump(mode="json") for o in before.observations},
        {o.id: o.model_dump(mode="json") for o in after.observations},
    )
    _diff_actions(entries, before, after)
    _diff_by_id(
        entries,
        DiffCategory.FAILURE_SEMANTIC,
        "failures",
        {f.id: f.model_dump(mode="json") for f in before.failures},
        {f.id: f.model_dump(mode="json") for f in after.failures},
    )
    _diff_by_id(
        entries,
        DiffCategory.BEHAVIOR,
        "transitions",
        {t.id: t.model_dump(mode="json") for t in before.transitions},
        {t.id: t.model_dump(mode="json") for t in after.transitions},
    )
    _diff_by_id(
        entries,
        DiffCategory.VERIFIER,
        "verifiers",
        {v.id: v.model_dump(mode="json") for v in before.verifiers},
        {v.id: v.model_dump(mode="json") for v in after.verifiers},
    )
    _diff_by_id(
        entries,
        DiffCategory.TASK,
        "tasks",
        {t.id: t.model_dump(mode="json") for t in before.tasks},
        {t.id: t.model_dump(mode="json") for t in after.tasks},
    )
    _diff_by_id(
        entries,
        DiffCategory.EVIDENCE_ONLY,
        "evidence_obligations",
        {e.id: e.model_dump(mode="json") for e in before.evidence_obligations},
        {e.id: e.model_dump(mode="json") for e in after.evidence_obligations},
    )

    for field in ("name", "version", "description", "declared_fidelity_level"):
        b = getattr(before, field)
        a = getattr(after, field)
        if b != a:
            entries.append(
                DiffEntry(
                    category=DiffCategory.META,
                    path=field,
                    change="modified",
                    before=b,
                    after=a,
                )
            )

    advisory, rationale = _advise_semver(entries)
    return DiffResult(entries=entries, advisory_semver=advisory, advisory_rationale=rationale)


def _diff_by_id(
    entries: list[DiffEntry],
    category: DiffCategory,
    prefix: str,
    before: dict[str, Any],
    after: dict[str, Any],
) -> None:
    for key in sorted(set(before) | set(after)):
        if key not in before:
            entries.append(
                DiffEntry(
                    category=category,
                    path=f"{prefix}.{key}",
                    change="added",
                    after=after[key],
                )
            )
        elif key not in after:
            entries.append(
                DiffEntry(
                    category=category,
                    path=f"{prefix}.{key}",
                    change="removed",
                    before=before[key],
                )
            )
        elif before[key] != after[key]:
            entries.append(
                DiffEntry(
                    category=category,
                    path=f"{prefix}.{key}",
                    change="modified",
                    before=before[key],
                    after=after[key],
                )
            )


def _diff_actions(
    entries: list[DiffEntry],
    before: WorldDefinition,
    after: WorldDefinition,
) -> None:
    bmap = {a.id: a for a in before.actions}
    amap = {a.id: a for a in after.actions}
    for key in sorted(set(bmap) | set(amap)):
        if key not in bmap:
            entries.append(
                DiffEntry(
                    category=DiffCategory.BEHAVIOR,
                    path=f"actions.{key}",
                    change="added",
                    after=amap[key].model_dump(mode="json"),
                )
            )
            continue
        if key not in amap:
            entries.append(
                DiffEntry(
                    category=DiffCategory.BEHAVIOR,
                    path=f"actions.{key}",
                    change="removed",
                    before=bmap[key].model_dump(mode="json"),
                )
            )
            continue
        b, a = bmap[key], amap[key]
        if b.authorization != a.authorization or b.actor_classes != a.actor_classes:
            entries.append(
                DiffEntry(
                    category=DiffCategory.PERMISSION,
                    path=f"actions.{key}.authorization",
                    change="modified",
                    before={"authorization": b.authorization, "actors": b.actor_classes},
                    after={"authorization": a.authorization, "actors": a.actor_classes},
                )
            )
        b_rest = b.model_dump(mode="json")
        a_rest = a.model_dump(mode="json")
        for drop in ("authorization", "actor_classes"):
            b_rest.pop(drop, None)
            a_rest.pop(drop, None)
        if b_rest != a_rest:
            entries.append(
                DiffEntry(
                    category=DiffCategory.BEHAVIOR,
                    path=f"actions.{key}",
                    change="modified",
                    before=b.model_dump(mode="json"),
                    after=a.model_dump(mode="json"),
                )
            )


def _advise_semver(entries: list[DiffEntry]) -> tuple[str, str]:
    if not entries:
        return "none", "No semantic differences."
    cats = {e.category for e in entries}
    breaking = {
        DiffCategory.STATE_SCHEMA,
        DiffCategory.BEHAVIOR,
        DiffCategory.PERMISSION,
        DiffCategory.FAILURE_SEMANTIC,
        DiffCategory.OBSERVATION,
    }
    if cats & breaking:
        return (
            "major",
            "Breaking semantic changes in state, behavior, permissions, failures, or observations.",
        )
    if DiffCategory.VERIFIER in cats or DiffCategory.TASK in cats:
        return "minor", "Task or verifier surface changed without core schema breaks."
    if DiffCategory.SOURCE_ONLY in cats or DiffCategory.EVIDENCE_ONLY in cats:
        return "patch", "Source or evidence-only changes."
    return "patch", "Metadata or non-breaking changes."
