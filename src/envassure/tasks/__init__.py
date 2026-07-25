"""Task generation from TaskTemplate with constrained sampling helpers."""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass
from typing import Any

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import TaskTemplate, WorldDefinition
from envassure.ir.primitives import ConstraintExpr


@dataclass(slots=True)
class GeneratedTask:
    """A concrete task instance derived from a template."""

    template_id: str
    task: TaskTemplate
    sample_index: int
    constraints: list[ConstraintExpr]
    metadata: dict[str, Any]


def generate_tasks(
    world: WorldDefinition,
    template: TaskTemplate | str,
    *,
    count: int = 1,
    seed: int = 0,
    strategy: str = "constrained",
) -> list[GeneratedTask]:
    """
    Generate concrete tasks from a TaskTemplate.

    Strategies:
    - constrained: sample actor assignments / budgets under template constraints
    - boundary: extremes of horizon and resource_budget
    - pairwise: pairwise actor-role combinations when multiple actors exist
    - mutation_negative: clone with prohibited_behavior emphasized
    """
    tmpl = _resolve_template(world, template)
    if strategy == "boundary":
        return _boundary_tasks(world, tmpl, count=count, seed=seed)
    if strategy == "pairwise":
        return _pairwise_tasks(world, tmpl, count=count, seed=seed)
    if strategy == "mutation_negative":
        return _mutation_negative_tasks(world, tmpl, count=count, seed=seed)
    return _constrained_tasks(world, tmpl, count=count, seed=seed)


def constrained_sample(
    domain: list[Any],
    *,
    count: int,
    seed: int,
    constraints: list[ConstraintExpr] | None = None,
) -> list[Any]:
    """
    Deterministic constrained sampling over a finite domain.

    Constraints are treated as opaque filters when ``structured`` contains
    ``{"equals": value}`` or ``{"in": [...]}``; otherwise all values are eligible.
    """
    eligible = list(domain)
    for constraint in constraints or []:
        eligible = [v for v in eligible if _satisfies(v, constraint)]
    if not eligible:
        return []
    out: list[Any] = []
    for i in range(count):
        idx = _stable_index(seed, i, len(eligible))
        out.append(eligible[idx])
    return out


def validate_release_tasks(
    world: WorldDefinition,
    tasks: list[TaskTemplate] | None = None,
) -> DiagnosticReport:
    """Validity gates for release-grade tasks."""
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    verifier_ids = {v.id for v in world.verifiers}
    target = tasks if tasks is not None else world.tasks
    for task in target:
        if not task.goal_claims:
            report.add(
                make_diagnostic(
                    "EAC6001",
                    reason=f"task {task.id!r} has empty goal_claims",
                    subject=task.id,
                )
            )
        if not task.verifier_claim_ids:
            report.add(
                make_diagnostic(
                    "EAC6001",
                    reason=f"task {task.id!r} has no verifier_claim_ids",
                    subject=task.id,
                )
            )
        for vid in task.verifier_claim_ids:
            if vid not in verifier_ids:
                report.add(
                    make_diagnostic(
                        "EAC6001",
                        reason=f"task {task.id!r} references unknown verifier {vid!r}",
                        subject=task.id,
                    )
                )
        # Solve-verify asymmetry: solvability_method mirrors model_judged verifier.
        for vid in task.verifier_claim_ids:
            for verifier in world.verifiers:
                if verifier.id != vid:
                    continue
                if (
                    task.solvability_method
                    and verifier.mechanism == "model_judged"
                    and "model" in (task.solvability_method or "")
                ):
                    report.add(
                        make_diagnostic(
                            "EAC6003",
                            reason=(
                                f"task {task.id!r} solvability_method and verifier "
                                f"{vid!r} both rely on model judgment"
                            ),
                            subject=task.id,
                        )
                    )
    return report


def _resolve_template(world: WorldDefinition, template: TaskTemplate | str) -> TaskTemplate:
    if isinstance(template, TaskTemplate):
        return template
    for task in world.tasks:
        if task.id == template:
            return task
    raise KeyError(f"unknown task template {template!r}")


def _constrained_tasks(
    world: WorldDefinition,
    tmpl: TaskTemplate,
    *,
    count: int,
    seed: int,
) -> list[GeneratedTask]:
    actor_ids = [a.id for a in world.actors]
    samples = constrained_sample(actor_ids, count=count, seed=seed) if actor_ids else [None] * count
    results: list[GeneratedTask] = []
    for i, sample in enumerate(samples):
        task = tmpl.model_copy(deep=True)
        task.id = f"{tmpl.id}.s{seed}.{i}"
        if sample is not None and not task.actor_assignment and world.actors:
            task.actor_assignment = {"primary": str(sample)}
        # Slight budget perturbation under seed.
        if task.resource_budget:
            budget = dict(task.resource_budget)
            for key, value in list(budget.items()):
                if isinstance(value, int | float):
                    budget[key] = value + ((seed + i) % 3)
            task.resource_budget = budget
        results.append(
            GeneratedTask(
                template_id=tmpl.id,
                task=task,
                sample_index=i,
                constraints=list(task.initial_constraints),
                metadata={"strategy": "constrained", "seed": seed},
            )
        )
    return results


def _boundary_tasks(
    world: WorldDefinition,
    tmpl: TaskTemplate,
    *,
    count: int,
    seed: int,
) -> list[GeneratedTask]:
    horizons = [1, tmpl.horizon or 1, max(tmpl.horizon or 1, 1) * 2]
    results: list[GeneratedTask] = []
    for i, horizon in enumerate(horizons[:count]):
        task = tmpl.model_copy(deep=True)
        task.id = f"{tmpl.id}.boundary.{seed}.{i}"
        task.horizon = horizon
        task.difficulty_factors = [*list(task.difficulty_factors), "boundary_horizon"]
        results.append(
            GeneratedTask(
                template_id=tmpl.id,
                task=task,
                sample_index=i,
                constraints=list(task.initial_constraints),
                metadata={"strategy": "boundary", "horizon": horizon},
            )
        )
    while len(results) < count:
        results.extend(_constrained_tasks(world, tmpl, count=1, seed=seed + len(results)))
        results = results[:count]
    return results


def _pairwise_tasks(
    world: WorldDefinition,
    tmpl: TaskTemplate,
    *,
    count: int,
    seed: int,
) -> list[GeneratedTask]:
    actors = [a.id for a in world.actors]
    pairs: list[tuple[str, ...]] = (
        list(itertools.combinations(actors, 2)) if len(actors) >= 2 else [(a,) for a in actors]
    )
    if not pairs:
        return _constrained_tasks(world, tmpl, count=count, seed=seed)
    results: list[GeneratedTask] = []
    for i, pair in enumerate(pairs[:count]):
        task = tmpl.model_copy(deep=True)
        task.id = f"{tmpl.id}.pair.{seed}.{i}"
        assignment = dict(task.actor_assignment)
        if len(pair) == 1:
            assignment["primary"] = pair[0]
        else:
            assignment["a"] = pair[0]
            assignment["b"] = pair[1]
        task.actor_assignment = assignment
        results.append(
            GeneratedTask(
                template_id=tmpl.id,
                task=task,
                sample_index=i,
                constraints=list(task.initial_constraints),
                metadata={"strategy": "pairwise", "pair": list(pair)},
            )
        )
    return results


def _mutation_negative_tasks(
    world: WorldDefinition,
    tmpl: TaskTemplate,
    *,
    count: int,
    seed: int,
) -> list[GeneratedTask]:
    results: list[GeneratedTask] = []
    for i in range(count):
        task = tmpl.model_copy(deep=True)
        task.id = f"{tmpl.id}.neg.{seed}.{i}"
        prohibited = list(task.prohibited_behavior) or ["violate_authorization"]
        task.prohibited_behavior = prohibited
        task.intent = f"[negative] {task.intent}"
        task.difficulty_factors = [*list(task.difficulty_factors), "mutation_negative"]
        results.append(
            GeneratedTask(
                template_id=tmpl.id,
                task=task,
                sample_index=i,
                constraints=list(task.initial_constraints),
                metadata={"strategy": "mutation_negative", "world": world.environment_id},
            )
        )
    return results


def _satisfies(value: Any, constraint: ConstraintExpr) -> bool:
    structured = constraint.structured
    if not structured:
        return True
    if "equals" in structured:
        return value == structured["equals"]
    if "in" in structured and isinstance(structured["in"], list):
        return value in structured["in"]
    if "not_equals" in structured:
        return value != structured["not_equals"]
    return True


def _stable_index(seed: int, i: int, modulus: int) -> int:
    digest = hashlib.sha256(f"{seed}:{i}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % modulus
