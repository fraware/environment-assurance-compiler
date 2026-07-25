"""Probe planner for differential validation."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.ir.models import WorldDefinition


class ProbeKind(StrEnum):
    NORMAL = "normal"
    BOUNDARY = "boundary"
    AUTH = "auth"
    TIMEOUT_RETRY = "timeout_retry"
    PARTIAL_FAILURE = "partial_failure"
    CONCURRENCY = "concurrency"
    STALE = "stale"
    DEPENDENCY = "dependency"
    IDEMPOTENCY = "idempotency"
    RECOVERY = "recovery"
    STOCHASTIC = "stochastic"
    TERMINATION = "termination"
    SEQUENCE = "sequence"
    PAIRWISE = "pairwise"


class Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ProbeKind
    action_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    actor_id: str | None = None
    notes: str | None = None
    expect_failure_id: str | None = None
    dimensions: list[str] = Field(default_factory=list)


_BOUNDARY_PAYLOADS: list[tuple[str, dict[str, Any]]] = [
    ("empty", {}),
    ("max", {"_boundary": "max", "n": 2**31 - 1}),
    ("min", {"_boundary": "min", "n": -(2**31)}),
    ("zero", {"_boundary": "zero", "n": 0}),
    ("neg", {"_boundary": "neg", "n": -1}),
    ("unicode", {"_boundary": "unicode", "label": "café-Δ"}),
    ("nested", {"_boundary": "nested", "obj": {"a": [1, 2], "b": None}}),
    ("large", {"_boundary": "large", "blob": "x" * 256}),
]


def plan_probes(
    world: WorldDefinition,
    *,
    kinds: list[ProbeKind] | None = None,
    max_probes: int = 128,
    expand: bool = True,
) -> list[Probe]:
    """
    Plan concealed differential probes covering semantic dimensions.

    When *expand* is true (default), fills the budget with payload variants,
    pairwise action sequences, seed grids for stochastic actions, and actor
    role variants so a single workflow can reach ≥100 probes.
    """
    selected = kinds or list(ProbeKind)
    # Prefer core kinds before expansion fillers.
    expand_kinds = {ProbeKind.SEQUENCE, ProbeKind.PAIRWISE}
    core: list[ProbeKind] = [k for k in selected if k not in expand_kinds]
    expansion: list[ProbeKind] = [k for k in selected if k in expand_kinds]
    if expand and ProbeKind.SEQUENCE not in expansion:
        expansion.append(ProbeKind.SEQUENCE)
    if expand and ProbeKind.PAIRWISE not in expansion:
        expansion.append(ProbeKind.PAIRWISE)

    probes: list[Probe] = []
    if not world.actions:
        return probes

    for kind in core:
        if len(probes) >= max_probes:
            break
        probes.extend(_probes_for_kind(world, kind, budget=max_probes - len(probes)))

    if expand and len(probes) < max_probes:
        probes.extend(_expand_variants(world, probes, budget=max_probes - len(probes)))

    for kind in expansion:
        if len(probes) >= max_probes:
            break
        probes.extend(_probes_for_kind(world, kind, budget=max_probes - len(probes)))

    if expand and len(probes) < max_probes:
        probes.extend(_pad_systematic(world, probes, budget=max_probes - len(probes)))

    return probes[:max_probes]


def _probes_for_kind(world: WorldDefinition, kind: ProbeKind, *, budget: int) -> list[Probe]:
    out: list[Probe] = []
    actions = world.actions
    actors = {a.actor_class: a for a in world.actors}

    def add(probe: Probe) -> None:
        if len(out) < budget:
            out.append(probe)

    if kind is ProbeKind.NORMAL:
        for action in actions:
            add(
                Probe(
                    id=f"normal.{action.id}",
                    kind=kind,
                    action_id=action.id,
                    payload={"mode": "happy_path"},
                    actor_id=_actor_for(action.actor_classes, actors),
                    dimensions=["success", "observation", "state"],
                )
            )
    elif kind is ProbeKind.BOUNDARY:
        for action in actions:
            for tag, payload in _BOUNDARY_PAYLOADS:
                add(
                    Probe(
                        id=f"boundary.{action.id}.{tag}",
                        kind=kind,
                        action_id=action.id,
                        payload=dict(payload),
                        notes=f"boundary:{tag}",
                        dimensions=["success", "failure"],
                    )
                )
    elif kind is ProbeKind.AUTH:
        for action in actions:
            if not action.authorization:
                continue
            add(
                Probe(
                    id=f"auth.{action.id}.denied",
                    kind=kind,
                    action_id=action.id,
                    payload={"actor_roles": []},
                    expect_failure_id=_auth_failure(world, action.id),
                    notes=f"expect denial for {action.authorization}",
                    dimensions=["authorization", "failure", "success"],
                )
            )
            add(
                Probe(
                    id=f"auth.{action.id}.wrong_role",
                    kind=kind,
                    action_id=action.id,
                    payload={"actor_roles": ["role:mutated_orphan"]},
                    expect_failure_id=_auth_failure(world, action.id),
                    dimensions=["authorization", "failure", "success"],
                )
            )
            for actor in world.actors:
                if actor.actor_class in action.actor_classes or actor.id in action.actor_classes:
                    add(
                        Probe(
                            id=f"auth.{action.id}.as.{actor.id}",
                            kind=kind,
                            action_id=action.id,
                            actor_id=actor.id,
                            payload={
                                "actor_roles": list(actor.roles),
                                "authority_source": actor.authority_source,
                            },
                            dimensions=["authorization", "success"],
                        )
                    )
    elif kind is ProbeKind.TIMEOUT_RETRY:
        for action in actions:
            if action.timeout_behavior is None and action.retry_behavior is None:
                continue
            for inject in ("timeout", "retry_exhausted", "retry_once"):
                add(
                    Probe(
                        id=f"timeout.{action.id}.{inject}",
                        kind=kind,
                        action_id=action.id,
                        payload={"inject": inject},
                        dimensions=["retry", "failure", "latency"],
                    )
                )
    elif kind is ProbeKind.PARTIAL_FAILURE:
        for failure in world.failures:
            if failure.transaction_effect != "partial":
                continue
            for action in actions:
                if failure.id in action.failure_ids:
                    add(
                        Probe(
                            id=f"partial.{action.id}.{failure.id}",
                            kind=kind,
                            action_id=action.id,
                            payload={"inject_failure": failure.id},
                            expect_failure_id=failure.id,
                            dimensions=["failure", "state", "success"],
                        )
                    )
    elif kind is ProbeKind.CONCURRENCY:
        if world.concurrency_model != "single_actor" and len(world.actors) >= 2:
            for action in actions[:3]:
                add(
                    Probe(
                        id=f"concurrency.{action.id}",
                        kind=kind,
                        action_id=action.id,
                        payload={"parallel_actors": [a.id for a in world.actors[:2]]},
                        dimensions=["success", "state"],
                    )
                )
        elif len(world.actors) >= 2:
            action = actions[0]
            add(
                Probe(
                    id=f"concurrency.{action.id}.interleave",
                    kind=kind,
                    action_id=action.id,
                    payload={"parallel_actors": [a.id for a in world.actors[:2]]},
                    dimensions=["success", "state"],
                )
            )
    elif kind is ProbeKind.STALE:
        for failure in world.failures:
            if failure.category != "stale_state":
                continue
            for action in actions:
                if failure.id in action.failure_ids:
                    add(
                        Probe(
                            id=f"stale.{action.id}",
                            kind=kind,
                            action_id=action.id,
                            payload={"stale": True},
                            expect_failure_id=failure.id,
                            dimensions=["failure", "state"],
                        )
                    )
    elif kind is ProbeKind.DEPENDENCY:
        for action in actions:
            if action.external_side_effects or world.external_dependencies:
                add(
                    Probe(
                        id=f"dependency.{action.id}",
                        kind=kind,
                        action_id=action.id,
                        payload={"dependency_down": True},
                        dimensions=["failure", "success"],
                    )
                )
    elif kind is ProbeKind.IDEMPOTENCY:
        for action in actions:
            if action.idempotency:
                for replay in (2, 3, 5):
                    add(
                        Probe(
                            id=f"idempotency.{action.id}.r{replay}",
                            kind=kind,
                            action_id=action.id,
                            payload={"replay": replay},
                            notes=f"idempotency={action.idempotency}",
                            dimensions=["idempotency", "state", "success"],
                        )
                    )
    elif kind is ProbeKind.RECOVERY:
        for action in actions:
            if action.compensation_action:
                add(
                    Probe(
                        id=f"recovery.{action.id}",
                        kind=kind,
                        action_id=action.id,
                        payload={"compensate": action.compensation_action},
                        dimensions=["success", "state"],
                    )
                )
    elif kind is ProbeKind.STOCHASTIC:
        for transition in world.transitions:
            if transition.kind != "stochastic":
                continue
            for samples in (30, 50, 100):
                for seed in range(4):
                    add(
                        Probe(
                            id=f"stochastic.{transition.action_id}.n{samples}.s{seed}",
                            kind=kind,
                            action_id=transition.action_id,
                            payload={
                                "samples": samples,
                                "seed": seed,
                                "branches": [
                                    {"id": b.id, "probability": b.probability}
                                    for b in transition.branches
                                ],
                            },
                            notes="statistical conformance sample budget",
                            dimensions=["success"],
                        )
                    )
    elif kind is ProbeKind.TERMINATION:
        for transition in world.transitions:
            for branch in transition.branches:
                if not branch.terminal:
                    continue
                add(
                    Probe(
                        id=f"termination.{transition.action_id}.{branch.id}",
                        kind=kind,
                        action_id=transition.action_id,
                        payload={"expect_terminal": True, "branch_id": branch.id},
                        dimensions=["success", "state"],
                    )
                )
        if world.tasks and not out:
            task = world.tasks[0]
            action = actions[0]
            add(
                Probe(
                    id=f"termination.horizon.{task.id}",
                    kind=kind,
                    action_id=action.id,
                    payload={"horizon": task.horizon},
                    notes="horizon truncation probe",
                    dimensions=["success"],
                )
            )
    elif kind is ProbeKind.SEQUENCE:
        # Multi-step sequences encoded in payload for connectors that honor them.
        seq_actions = [a.id for a in actions[:4]]
        if len(seq_actions) >= 2:
            for length in range(2, min(5, len(seq_actions) + 1)):
                seq = seq_actions[:length]
                add(
                    Probe(
                        id=f"sequence.{'.'.join(seq)}",
                        kind=kind,
                        action_id=seq[-1],
                        payload={"sequence": seq, "mode": "ordered"},
                        dimensions=["success", "state", "observation"],
                    )
                )
    elif kind is ProbeKind.PAIRWISE:
        ids = [a.id for a in actions]
        for i, left in enumerate(ids):
            for right in ids[i:]:
                add(
                    Probe(
                        id=f"pairwise.{left}.{right}",
                        kind=kind,
                        action_id=right,
                        payload={"pair": [left, right]},
                        dimensions=["success", "state"],
                    )
                )
    return out


def _expand_variants(
    world: WorldDefinition,
    existing: list[Probe],
    *,
    budget: int,
) -> list[Probe]:
    """Clone existing probes with payload / seed variants until budget fills."""
    out: list[Probe] = []
    if budget <= 0:
        return out
    seen = {p.id for p in existing}
    variants = (
        {"variant": "dup", "noise": 0},
        {"variant": "dup", "noise": 1},
        {"variant": "alt", "flag": True},
        {"variant": "alt", "flag": False},
    )
    for probe in existing:
        for idx, extra in enumerate(variants):
            if len(out) >= budget:
                return out
            new_id = f"{probe.id}.v{idx}"
            if new_id in seen:
                continue
            seen.add(new_id)
            out.append(
                Probe(
                    id=new_id,
                    kind=probe.kind,
                    action_id=probe.action_id,
                    payload={**probe.payload, **extra},
                    actor_id=probe.actor_id,
                    notes=probe.notes,
                    expect_failure_id=probe.expect_failure_id,
                    dimensions=list(probe.dimensions),
                )
            )
    return out


def _pad_systematic(
    world: WorldDefinition,
    existing: list[Probe],
    *,
    budget: int,
) -> list[Probe]:
    """Systematic action x payload x actor grid to guarantee large probe counts."""
    out: list[Probe] = []
    seen = {p.id for p in existing}
    actor_ids: list[str | None] = [a.id for a in world.actors] or [None]
    payloads = [p for _, p in _BOUNDARY_PAYLOADS] + [
        {"mode": "happy_path", "i": i} for i in range(8)
    ]
    idx = 0
    while len(out) < budget:
        action = world.actions[idx % len(world.actions)]
        actor_id = actor_ids[idx % len(actor_ids)]
        payload = dict(payloads[idx % len(payloads)])
        payload["grid_index"] = idx
        new_id = f"grid.{action.id}.{idx}"
        idx += 1
        if new_id in seen:
            if idx > budget * 4:
                break
            continue
        seen.add(new_id)
        out.append(
            Probe(
                id=new_id,
                kind=ProbeKind.BOUNDARY,
                action_id=action.id,
                payload=payload,
                actor_id=actor_id,
                notes="systematic grid pad",
                dimensions=["success", "observation", "state"],
            )
        )
    return out


def _actor_for(
    classes: list[str],
    actors: dict[str, Any],
) -> str | None:
    for cls in classes:
        if cls in actors:
            return actors[cls].id
    return None


def _auth_failure(world: WorldDefinition, action_id: str) -> str | None:
    for action in world.actions:
        if action.id != action_id:
            continue
        for fid in action.failure_ids:
            for failure in world.failures:
                if failure.id == fid and failure.category == "authorization":
                    return fid
        return action.failure_ids[0] if action.failure_ids else None
    return None
