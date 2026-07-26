"""Validation pipeline v2 with release profiles (EAC-R09)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from envassure.analysis.static import StaticAnalysisResult, analyze_world
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic, DiagnosticReport, Severity
from envassure.expressions import validate_expression
from envassure.expressions.parser import parse_effect
from envassure.ir.models import WorldDefinition
from envassure.ir.primitives import ProvenanceRef
from envassure.obligations import validate_obligations
from envassure.runtime.authorization import compile_authorization
from envassure.runtime.observations import validate_observation_projections
from envassure.tasks import validate_release_tasks
from envassure.verifiers import audit_verifiers


class ReleaseProfile(str, Enum):
    """Named release profiles with escalating diagnostic→blocking maps."""

    AUTHORING = "authoring"
    EXECUTABLE = "executable"
    DIFFERENTIAL = "differential"
    RESEARCH_RELEASE = "research_release"
    DEPLOYMENT_CALIBRATION = "deployment_calibration"


PIPELINE_PASSES: tuple[str, ...] = (
    "schema",
    "provenance",
    "refs",
    "types",
    "transitions",
    "authorization",
    "info_flow",
    "task_satisfiability",
    "verifiers",
    "obligations",
    "runtime_support",
    "release_readiness",
)

# Codes elevated to ERROR under the named profile (and all stricter profiles).
_PROFILE_ELEVATIONS: dict[ReleaseProfile, frozenset[str]] = {
    ReleaseProfile.AUTHORING: frozenset(),
    ReleaseProfile.EXECUTABLE: frozenset(
        {
            "EAC5004",
            "EAC5005",
            "EAC4002",  # solvability
            "EAC4009",  # unreachable
        }
    ),
    ReleaseProfile.DIFFERENTIAL: frozenset(
        {
            "EAC5004",
            "EAC5005",
            "EAC4002",
            "EAC4009",
            "EAC7006",
        }
    ),
    ReleaseProfile.RESEARCH_RELEASE: frozenset(
        {
            "EAC5003",
            "EAC5004",
            "EAC5005",
            "EAC4002",
            "EAC4003",
            "EAC4006",
            "EAC4007",
            "EAC4009",
            "EAC6001",
            "EAC6003",
            "EAC7006",
        }
    ),
    ReleaseProfile.DEPLOYMENT_CALIBRATION: frozenset(
        {
            "EAC5003",
            "EAC5004",
            "EAC5005",
            "EAC4002",
            "EAC4003",
            "EAC4005",
            "EAC4006",
            "EAC4007",
            "EAC4009",
            "EAC6001",
            "EAC6003",
            "EAC7002",
            "EAC7006",
        }
    ),
}

_PROFILE_ORDER: tuple[ReleaseProfile, ...] = (
    ReleaseProfile.AUTHORING,
    ReleaseProfile.EXECUTABLE,
    ReleaseProfile.DIFFERENTIAL,
    ReleaseProfile.RESEARCH_RELEASE,
    ReleaseProfile.DEPLOYMENT_CALIBRATION,
)


def parse_release_profile(value: str | ReleaseProfile | None) -> ReleaseProfile:
    if value is None:
        return ReleaseProfile.AUTHORING
    if isinstance(value, ReleaseProfile):
        return value
    text = value.strip().lower().replace("-", "_")
    aliases = {
        "baseline": ReleaseProfile.AUTHORING,
        "author": ReleaseProfile.AUTHORING,
        "exec": ReleaseProfile.EXECUTABLE,
        "runtime": ReleaseProfile.EXECUTABLE,
        "diff": ReleaseProfile.DIFFERENTIAL,
        "research": ReleaseProfile.RESEARCH_RELEASE,
        "release": ReleaseProfile.RESEARCH_RELEASE,
        "deploy": ReleaseProfile.DEPLOYMENT_CALIBRATION,
        "deployment": ReleaseProfile.DEPLOYMENT_CALIBRATION,
        "calibration": ReleaseProfile.DEPLOYMENT_CALIBRATION,
    }
    if text in aliases:
        return aliases[text]
    try:
        return ReleaseProfile(text)
    except ValueError as exc:
        raise ValueError(
            f"unknown release profile {value!r}; expected one of "
            + ", ".join(p.value for p in ReleaseProfile)
        ) from exc


@dataclass(slots=True)
class PipelineResult:
    """Aggregate validation pipeline output."""

    report: DiagnosticReport
    profile: ReleaseProfile
    passes_run: list[str] = field(default_factory=list)
    static: StaticAnalysisResult | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def has_errors(self) -> bool:
        return self.report.has_errors()


def run_validation_pipeline(
    world: WorldDefinition,
    *,
    profile: str | ReleaseProfile = ReleaseProfile.AUTHORING,
    bfs_bound: int = 64,
) -> PipelineResult:
    """
    Run ordered validation passes and apply the profile diagnostic→blocking map.

    Passes: schema → refs → types → transitions → authorization → info-flow →
    task satisfiability → verifiers → obligations → runtime support → release readiness.
    """
    release = parse_release_profile(profile)
    report = DiagnosticReport(
        context={
            "environment_id": world.environment_id,
            "release_profile": release.value,
        }
    )
    passes_run: list[str] = []
    static: StaticAnalysisResult | None = None
    details: dict[str, Any] = {"profile": release.value}

    # --- schema ---
    passes_run.append("schema")
    _pass_schema(world, report)

    # --- provenance origin_kind integrity ---
    passes_run.append("provenance")
    _pass_provenance_origins(world, report)

    # --- refs + types (reference integrity foundation) ---
    passes_run.append("refs")
    passes_run.append("types")
    _pass_refs_and_types(world, report)

    deeper = release != ReleaseProfile.AUTHORING
    if deeper:
        static = analyze_world(world, bfs_bound=bfs_bound)
        report.extend(static.report.diagnostics)
        details["static"] = static.details
        passes_run.extend(
            [
                "transitions",
                "authorization",
                "info_flow",
                "task_satisfiability",
            ]
        )
    else:
        # Authoring still runs lightweight observation path checks (non-elevated).
        passes_run.append("info_flow")
        obs = validate_observation_projections(
            world,
            require_actor_bindings=False,
            strict_unsupported=False,
        )
        report.extend(obs.diagnostics)

    # --- verifiers ---
    passes_run.append("verifiers")
    if release in {
        ReleaseProfile.EXECUTABLE,
        ReleaseProfile.DIFFERENTIAL,
        ReleaseProfile.RESEARCH_RELEASE,
        ReleaseProfile.DEPLOYMENT_CALIBRATION,
    }:
        report.extend(audit_verifiers(world).diagnostics)

    # --- obligations ---
    passes_run.append("obligations")
    if release in {
        ReleaseProfile.EXECUTABLE,
        ReleaseProfile.DIFFERENTIAL,
        ReleaseProfile.RESEARCH_RELEASE,
        ReleaseProfile.DEPLOYMENT_CALIBRATION,
    }:
        report.extend(validate_obligations(world).diagnostics)

    # --- runtime support (expressions, auth, observations) ---
    passes_run.append("runtime_support")
    if release != ReleaseProfile.AUTHORING:
        _pass_runtime_support(world, report, profile=release)

    # --- tasks (release-oriented) ---
    if release in {
        ReleaseProfile.DIFFERENTIAL,
        ReleaseProfile.RESEARCH_RELEASE,
        ReleaseProfile.DEPLOYMENT_CALIBRATION,
    } or (release == ReleaseProfile.EXECUTABLE and world.tasks):
        # Executable checks tasks when present; research+ always.
        report.extend(validate_release_tasks(world).diagnostics)

    # --- release readiness ---
    passes_run.append("release_readiness")
    _pass_release_readiness(world, report, profile=release)

    elevated = apply_profile_blocking(report, release)
    return PipelineResult(
        report=elevated,
        profile=release,
        passes_run=passes_run,
        static=static,
        details=details,
    )


def apply_profile_blocking(
    report: DiagnosticReport,
    profile: ReleaseProfile,
) -> DiagnosticReport:
    """Return a new report with profile-elevated severities."""
    elevate = _elevated_codes(profile)
    out = DiagnosticReport(context=dict(report.context))
    out.context["release_profile"] = profile.value
    for diag in report.diagnostics:
        if diag.code in elevate and diag.severity is not Severity.ERROR:
            out.add(
                Diagnostic(
                    code=diag.code,
                    severity=Severity.ERROR,
                    summary=diag.summary,
                    subject=diag.subject,
                    source_refs=list(diag.source_refs),
                    affected_artifacts=list(diag.affected_artifacts),
                    consequence=diag.consequence,
                    suggested_repair=diag.suggested_repair,
                    details={**diag.details, "elevated_by_profile": profile.value},
                )
            )
        else:
            out.add(diag)
    return out


def _elevated_codes(profile: ReleaseProfile) -> frozenset[str]:
    codes: set[str] = set()
    for candidate in _PROFILE_ORDER:
        codes |= set(_PROFILE_ELEVATIONS.get(candidate, frozenset()))
        if candidate is profile:
            break
    # Authoring elevates nothing beyond native ERROR severities.
    if profile is ReleaseProfile.AUTHORING:
        return frozenset()
    return frozenset(codes)


def _pass_schema(world: WorldDefinition, report: DiagnosticReport) -> None:
    if not world.environment_id.strip():
        report.add(
            make_diagnostic(
                "EAC3001",
                reason="environment_id is empty",
                subject=world.name,
            )
        )
    if not world.name.strip():
        report.add(
            make_diagnostic(
                "EAC3001",
                reason="name is empty",
                subject=world.environment_id,
            )
        )


def _pass_provenance_origins(world: WorldDefinition, report: DiagnosticReport) -> None:
    """Reject provenance that claims source_derived for inferred/conflict origins."""
    from envassure.ir.primitives import ORIGIN_KINDS, validate_provenance_origin

    for kind, element_id, provenance in _iter_element_provenance(world):
        subject = f"{kind}:{element_id}"
        if provenance.origin_kind is not None and provenance.origin_kind not in ORIGIN_KINDS:
            report.add(
                make_diagnostic(
                    "EAC3008",
                    subject=subject,
                    reason=f"unknown origin_kind {provenance.origin_kind!r}",
                )
            )
            continue
        # Open ambiguities must not claim source_derived / human_decision without a decision.
        if kind == "ambiguity":
            amb = next(a for a in world.ambiguities if a.id == element_id)
            if amb.status == "open" and provenance.origin_kind in {
                "source_derived",
                "human_decision",
            }:
                report.add(
                    make_diagnostic(
                        "EAC3008",
                        subject=subject,
                        reason=(
                            f"open ambiguity cannot use origin_kind={provenance.origin_kind!r}; "
                            "use unresolved_conflict until decided"
                        ),
                    )
                )
        # Notes may carry an explicit derivation hint used by compilers/tests.
        note = (provenance.notes or "").lower()
        derivation_hints: list[str] = []
        if "derivation_class=inferred" in note or "derivation:inferred" in note:
            derivation_hints.append("inferred")
        if "derivation_class=direct" in note or "derivation:direct" in note:
            derivation_hints.append("direct")
        reason = validate_provenance_origin(
            provenance,
            derivation_classes=derivation_hints,
            subject=subject,
        )
        if reason:
            report.add(
                make_diagnostic(
                    "EAC3008",
                    subject=subject,
                    reason=reason,
                )
            )


def _iter_element_provenance(
    world: WorldDefinition,
) -> Iterator[tuple[str, str, ProvenanceRef]]:
    for state in world.state:
        yield "state", state.id, state.provenance
    for action in world.actions:
        yield "action", action.id, action.provenance
    for actor in world.actors:
        yield "actor", actor.id, actor.provenance
    for transition in world.transitions:
        yield "transition", transition.id, transition.provenance
    for observation in world.observations:
        yield "observation", observation.id, observation.provenance
    for failure in world.failures:
        yield "failure", failure.id, failure.provenance
    for task in world.tasks:
        yield "task", task.id, task.provenance
    for verifier in world.verifiers:
        yield "verifier", verifier.id, verifier.provenance
    for obligation in world.evidence_obligations:
        yield "evidence_obligation", obligation.id, obligation.provenance
    for ambiguity in world.ambiguities:
        yield "ambiguity", ambiguity.id, ambiguity.provenance
    yield "world", world.environment_id, world.provenance


def _pass_refs_and_types(world: WorldDefinition, report: DiagnosticReport) -> None:
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
    _check_unique(report, "observations", [o.id for o in world.observations])

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
            report.add(
                make_diagnostic(
                    "EAC5005",
                    reason=(
                        f"actor {actor.id!r} references unknown observation "
                        f"projection {actor.observation_projection_id!r}"
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


def _pass_runtime_support(
    world: WorldDefinition,
    report: DiagnosticReport,
    *,
    profile: ReleaseProfile,
) -> None:
    require_bindings = profile in {
        ReleaseProfile.EXECUTABLE,
        ReleaseProfile.DIFFERENTIAL,
        ReleaseProfile.RESEARCH_RELEASE,
        ReleaseProfile.DEPLOYMENT_CALIBRATION,
    }
    obs_report = validate_observation_projections(
        world,
        require_actor_bindings=require_bindings,
        strict_unsupported=True,
    )
    report.extend(obs_report.diagnostics)

    for action in world.actions:
        if action.authorization:
            try:
                compile_authorization(action.authorization)
            except ValueError as exc:
                report.add(
                    make_diagnostic(
                        "EAC4004",
                        reason=(
                            f"action {action.id!r} authorization "
                            f"{action.authorization!r} failed to compile: {exc}"
                        ),
                        subject=action.id,
                        affected_artifacts=[f"action:{action.id}"],
                    )
                )
        for effect in action.intended_effects + action.resource_effects:
            for part in _split_effect_parts(effect):
                if not _looks_like_assignment(part):
                    # Documentary / non-assignment strings are ignored by the
                    # expression compiler; they do not silently become executable.
                    continue
                try:
                    parse_effect(part)
                except Exception as exc:
                    report.add(
                        make_diagnostic(
                            "EAC4001",
                            reason=(
                                f"action {action.id!r} effect {part!r} failed to compile: {exc}"
                            ),
                            subject=action.id,
                        )
                    )
        for constraint in action.preconditions:
            raw = constraint.expression
            structured = constraint.structured
            if not raw and not structured:
                continue
            _expr, diags = validate_expression(raw, structured=structured or None)
            for diag in diags:
                report.add(
                    make_diagnostic(
                        "EAC4010",
                        reason=(
                            f"action {action.id!r} precondition failed expression "
                            f"compile: {diag.message}"
                        ),
                        subject=action.id,
                    )
                )

    for transition in world.transitions:
        guard = transition.guard
        if guard is None:
            continue
        raw = guard.expression
        structured = guard.structured
        if not raw and not structured:
            continue
        _expr, diags = validate_expression(raw, structured=structured or None)
        for diag in diags:
            report.add(
                make_diagnostic(
                    "EAC4010",
                    reason=(
                        f"transition {transition.id!r} guard failed "
                        f"expression compile: {diag.message}"
                    ),
                    subject=transition.id,
                )
            )


def _pass_release_readiness(
    world: WorldDefinition,
    report: DiagnosticReport,
    *,
    profile: ReleaseProfile,
) -> None:
    if profile is ReleaseProfile.AUTHORING:
        return

    open_ambiguities = [a for a in world.ambiguities if a.status == "open"]
    if open_ambiguities and profile in {
        ReleaseProfile.RESEARCH_RELEASE,
        ReleaseProfile.DEPLOYMENT_CALIBRATION,
    }:
        report.add(
            make_diagnostic(
                "EAC3007",
                profile=profile.value,
                reason=(
                    f"{len(open_ambiguities)} open ambiguities block "
                    f"{profile.value} (e.g. {open_ambiguities[0].id!r})"
                ),
                subject=world.environment_id,
                details={"open_ambiguity_ids": [a.id for a in open_ambiguities]},
            )
        )

    if profile in {
        ReleaseProfile.DIFFERENTIAL,
        ReleaseProfile.RESEARCH_RELEASE,
        ReleaseProfile.DEPLOYMENT_CALIBRATION,
    }:
        # Actors that can act must have projections for differential evidence.
        for actor in world.actors:
            if actor.available_actions and not actor.observation_projection_id:
                report.add(
                    make_diagnostic(
                        "EAC3007",
                        profile=profile.value,
                        reason=(
                            f"actor {actor.id!r} missing observation_projection_id "
                            f"under {profile.value}"
                        ),
                        subject=actor.id,
                    )
                )

    if profile is ReleaseProfile.DEPLOYMENT_CALIBRATION and world.declared_fidelity_level in {
        "",
        "EF-0",
    }:
        report.add(
            make_diagnostic(
                "EAC3007",
                profile=profile.value,
                reason=(
                    "deployment_calibration requires declared_fidelity_level "
                    f"above EF-0 (got {world.declared_fidelity_level!r})"
                ),
                subject=world.environment_id,
            )
        )


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


def _split_effect_parts(effect: str) -> list[str]:
    return [part.strip() for part in effect.split(";") if part.strip()]


def _looks_like_assignment(effect: str) -> bool:
    return any(op in effect for op in ("+=", "-=", "="))
