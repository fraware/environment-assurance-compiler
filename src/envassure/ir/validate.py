"""IR semantic validation (reference integrity foundation)."""

from __future__ import annotations

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import WorldDefinition


def validate_world(world: WorldDefinition) -> DiagnosticReport:
    """Type/reference integrity checks for a WorldDefinition."""
    report = DiagnosticReport(context={"environment_id": world.environment_id})

    if not world.environment_id.strip():
        report.add(
            make_diagnostic(
                "EAC3001",
                reason="environment_id is empty",
                subject=world.name,
            )
        )

    state_ids = {s.id for s in world.state}
    action_ids = {a.id for a in world.actions}
    actor_ids = {a.id for a in world.actors}
    actor_classes = {a.actor_class for a in world.actors}
    failure_ids = {f.id for f in world.failures}
    verifier_ids = {v.id for v in world.verifiers}
    observation_ids = {o.id for o in world.observations}

    _check_unique(report, "state", [s.id for s in world.state])
    _check_unique(report, "actions", [a.id for a in world.actions])
    _check_unique(report, "actors", [a.id for a in world.actors])
    _check_unique(report, "transitions", [t.id for t in world.transitions])
    _check_unique(report, "tasks", [t.id for t in world.tasks])
    _check_unique(report, "verifiers", [v.id for v in world.verifiers])

    for action in world.actions:
        for cls in action.actor_classes:
            if cls not in actor_classes and cls not in actor_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"action {action.id!r} references unknown actor class {cls!r}",
                        subject=action.id,
                        affected_artifacts=[f"action:{action.id}"],
                    )
                )
        for fid in action.failure_ids:
            if fid not in failure_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"action {action.id!r} references unknown failure {fid!r}",
                        subject=action.id,
                    )
                )
        for path in action.reads + action.writes:
            root = path.split(".", 1)[0]
            if root not in state_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"action {action.id!r} references unknown state {root!r}",
                        subject=action.id,
                    )
                )
        if action.retry_behavior is None and action.timeout_behavior is not None:
            report.add(
                make_diagnostic(
                    "EAC4027",
                    action_id=action.id,
                    subject=action.id,
                    affected_artifacts=[f"action:{action.id}"],
                )
            )

    for actor in world.actors:
        if (
            actor.observation_projection_id
            and actor.observation_projection_id not in observation_ids
        ):
            report.add(
                make_diagnostic(
                    "EAC3002",
                    reason=(
                        f"actor {actor.id!r} references unknown observation "
                        f"{actor.observation_projection_id!r}"
                    ),
                    subject=actor.id,
                )
            )
        for aid in actor.available_actions:
            if aid not in action_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"actor {actor.id!r} references unknown action {aid!r}",
                        subject=actor.id,
                    )
                )

    for obs in world.observations:
        if obs.target_actor_class not in actor_classes and obs.target_actor_class not in actor_ids:
            report.add(
                make_diagnostic(
                    "EAC3002",
                    reason=(
                        f"observation {obs.id!r} targets unknown actor class "
                        f"{obs.target_actor_class!r}"
                    ),
                    subject=obs.id,
                )
            )
        for path in obs.visible_paths:
            root = path.split(".", 1)[0]
            if root not in state_ids:
                report.add(
                    make_diagnostic(
                        "EAC5001",
                        reason=f"observation {obs.id!r} visible path unknown state {root!r}",
                        subject=obs.id,
                    )
                )

    for transition in world.transitions:
        if transition.action_id not in action_ids:
            report.add(
                make_diagnostic(
                    "EAC3002",
                    reason=(
                        f"transition {transition.id!r} references unknown action "
                        f"{transition.action_id!r}"
                    ),
                    subject=transition.id,
                )
            )
        if not transition.branches:
            report.add(
                make_diagnostic(
                    "EAC4001",
                    reason=f"transition {transition.id!r} has no branches",
                    subject=transition.id,
                )
            )

    for task in world.tasks:
        for vid in task.verifier_claim_ids:
            if vid not in verifier_ids:
                report.add(
                    make_diagnostic(
                        "EAC3002",
                        reason=f"task {task.id!r} references unknown verifier {vid!r}",
                        subject=task.id,
                    )
                )

    for ambiguity in world.ambiguities:
        if ambiguity.status == "open":
            report.add(
                make_diagnostic(
                    "EAC2001",
                    ambiguity_id=ambiguity.id,
                    subject=ambiguity.subject,
                    consequence=ambiguity.operational_consequence,
                )
            )

    return report


def _check_unique(report: DiagnosticReport, kind: str, ids: list[str]) -> None:
    seen: set[str] = set()
    for item_id in ids:
        if item_id in seen:
            report.add(
                make_diagnostic(
                    "EAC3003",
                    reason=f"duplicate {kind} id {item_id!r}",
                    subject=item_id,
                )
            )
        seen.add(item_id)
