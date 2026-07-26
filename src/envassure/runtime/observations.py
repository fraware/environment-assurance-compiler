"""Executable observation projections — fail-closed (EAC-R08)."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic, DiagnosticReport
from envassure.ir.models import ActorDefinition, ObservationProjection, WorldDefinition
from envassure.runtime.authorization import (
    AuthDecision,
    AuthExpr,
    compile_authorization,
    evaluate_authorization,
)

_MISSING = object()

_NOOP_TOKENS = frozenset({"", "none", "identity", "noop", "n/a", "na"})
_SUPPORTED_AGGREGATIONS = frozenset({"", "none", "identity"})
_SUPPORTED_ERROR_POLICIES = frozenset({"", "none", "omit", "fail"})
_RENAME_RE = re.compile(r"^rename:(.+?)->(.+)$", re.IGNORECASE)
_REDACT_RE = re.compile(r"^(?:redact|mask|omit):(.+)$", re.IGNORECASE)


class ObservationError(RuntimeError):
    """Fail-closed observation projection failure."""

    def __init__(self, message: str, *, reason_code: str = "observation_denied") -> None:
        super().__init__(message)
        self.reason_code = reason_code


TransformationKind = Literal["redact", "omit", "rename"]


@dataclass(frozen=True, slots=True)
class CompiledTransformation:
    kind: TransformationKind
    path: str
    rename_to: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledObservation:
    """Compiled, executable observation projection."""

    projection_id: str
    visible_paths: tuple[str, ...]
    omitted_paths: tuple[str, ...]
    transformations: tuple[CompiledTransformation, ...] = ()
    access_control: str | None = None
    access_control_ast: AuthExpr | None = None
    deny_labels: frozenset[str] = frozenset()
    error_policy: Literal["omit", "fail"] = "fail"
    unsupported: tuple[str, ...] = ()
    allow_empty_visible: bool = False


@dataclass(slots=True)
class ObservationCompileResult:
    compiled: CompiledObservation | None
    diagnostics: list[Diagnostic] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.compiled is not None and not self.unsupported


def is_noop_semantic(value: str | None) -> bool:
    if value is None:
        return True
    return value.strip().lower() in _NOOP_TOKENS


def compile_observation(
    proj: ObservationProjection,
    *,
    strict_unsupported: bool = True,
) -> ObservationCompileResult:
    """Compile declared ObservationProjection fields; collect unsupported semantics."""
    diagnostics: list[Diagnostic] = []
    unsupported: list[str] = []

    def _reject(field_name: str, raw: str) -> None:
        msg = f"observation {proj.id!r} field {field_name}={raw!r} is not executable"
        unsupported.append(msg)
        if strict_unsupported:
            diagnostics.append(
                make_diagnostic(
                    "EAC5004",
                    reason=msg,
                    subject=proj.id,
                    details={"field": field_name, "value": raw},
                    affected_artifacts=[f"observation:{proj.id}"],
                )
            )

    if not is_noop_semantic(proj.delay):
        _reject("delay", str(proj.delay))
    if not is_noop_semantic(proj.noise):
        _reject("noise", str(proj.noise))
    if not is_noop_semantic(proj.staleness):
        _reject("staleness", str(proj.staleness))
    if not is_noop_semantic(proj.side_channel_policy):
        _reject("side_channel_policy", str(proj.side_channel_policy))

    agg = (proj.aggregation or "").strip().lower()
    if agg and agg not in _SUPPORTED_AGGREGATIONS:
        _reject("aggregation", str(proj.aggregation))

    error_raw = (proj.error_policy or "fail").strip().lower()
    if error_raw not in _SUPPORTED_ERROR_POLICIES:
        _reject("error_policy", str(proj.error_policy))
        error_policy: Literal["omit", "fail"] = "fail"
    else:
        error_policy = "omit" if error_raw == "omit" else "fail"

    transformations: list[CompiledTransformation] = []
    for raw in proj.transformations:
        compiled_t = _compile_transformation(raw)
        if compiled_t is None:
            _reject("transformations", raw)
        else:
            transformations.append(compiled_t)

    access_expr: AuthExpr | None = None
    if proj.access_control and not is_noop_semantic(proj.access_control):
        try:
            access_expr = compile_authorization(proj.access_control)
        except ValueError as exc:
            msg = (
                f"observation {proj.id!r} access_control={proj.access_control!r} "
                f"failed to compile: {exc}"
            )
            unsupported.append(msg)
            if strict_unsupported:
                diagnostics.append(
                    make_diagnostic(
                        "EAC5004",
                        reason=msg,
                        subject=proj.id,
                        details={"field": "access_control", "value": proj.access_control},
                        affected_artifacts=[f"observation:{proj.id}"],
                    )
                )

    deny_labels: set[str] = set()
    for label in proj.information_flow_labels:
        if ":" not in label:
            # Bare labels are documentary unless they look like executable claims.
            if label.strip() and not is_noop_semantic(label):
                # Allow free-form tags; only state:mapping forms are enforced.
                continue
            continue
        state_id, _, mapping = label.partition(":")
        mapping_l = mapping.strip().lower()
        if mapping_l in {"deny", "omit", "hidden", "evaluator", "secret"}:
            deny_labels.add(state_id.strip())
        elif mapping_l in {
            "allow",
            "visible",
            "policy",
            "policy_visible",
            "public",
            "internal",
        }:
            continue
        elif mapping_l and not is_noop_semantic(mapping):
            _reject("information_flow_labels", label)

    if not proj.visible_paths and not proj.omitted_paths:
        # Empty allow-list and omit-list ⇒ deny-all (fail closed), not full state.
        pass

    if unsupported and strict_unsupported:
        return ObservationCompileResult(
            compiled=None,
            diagnostics=diagnostics,
            unsupported=unsupported,
        )

    access_raw = (
        None
        if access_expr is None or is_noop_semantic(proj.access_control)
        else str(proj.access_control)
    )
    compiled = CompiledObservation(
        projection_id=proj.id,
        visible_paths=tuple(proj.visible_paths),
        omitted_paths=tuple(proj.omitted_paths),
        transformations=tuple(transformations),
        access_control=access_raw,
        access_control_ast=access_expr,
        deny_labels=frozenset(deny_labels),
        error_policy=error_policy,
        unsupported=tuple(unsupported),
        allow_empty_visible=bool(proj.omitted_paths) and not proj.visible_paths,
    )
    return ObservationCompileResult(
        compiled=compiled,
        diagnostics=diagnostics,
        unsupported=unsupported,
    )


def validate_observation_projections(
    world: WorldDefinition,
    *,
    require_actor_bindings: bool = False,
    strict_unsupported: bool = True,
) -> DiagnosticReport:
    """Validate/compile every ObservationProjection; optionally require actor bindings."""
    report = DiagnosticReport(context={"environment_id": world.environment_id})
    observation_ids = {o.id for o in world.observations}
    state_ids = {s.id for s in world.state}

    for proj in world.observations:
        result = compile_observation(proj, strict_unsupported=strict_unsupported)
        report.extend(result.diagnostics)
        if not result.ok and not result.diagnostics:
            for msg in result.unsupported:
                report.add(
                    make_diagnostic(
                        "EAC5004",
                        reason=msg,
                        subject=proj.id,
                        affected_artifacts=[f"observation:{proj.id}"],
                    )
                )
        for path in list(proj.visible_paths) + list(proj.omitted_paths):
            root = path.split(".", 1)[0]
            if root not in state_ids:
                report.add(
                    make_diagnostic(
                        "EAC5001",
                        reason=(
                            f"observation {proj.id!r} path {path!r} references "
                            f"unknown state {root!r}"
                        ),
                        subject=proj.id,
                    )
                )
        if not proj.visible_paths and not proj.omitted_paths:
            report.add(
                make_diagnostic(
                    "EAC5005",
                    reason=(
                        f"observation {proj.id!r} declares neither visible_paths "
                        "nor omitted_paths (would be deny-all at runtime)"
                    ),
                    subject=proj.id,
                    affected_artifacts=[f"observation:{proj.id}"],
                )
            )

    for actor in world.actors:
        proj_id = actor.observation_projection_id
        if not proj_id:
            if require_actor_bindings and actor.available_actions:
                report.add(
                    make_diagnostic(
                        "EAC5005",
                        reason=(
                            f"actor {actor.id!r} has available_actions but no "
                            "observation_projection_id (full-state observe is forbidden)"
                        ),
                        subject=actor.id,
                        affected_artifacts=[f"actor:{actor.id}"],
                    )
                )
            continue
        if proj_id not in observation_ids:
            report.add(
                make_diagnostic(
                    "EAC5005",
                    reason=(
                        f"actor {actor.id!r} references unknown observation projection {proj_id!r}"
                    ),
                    subject=actor.id,
                    affected_artifacts=[f"actor:{actor.id}"],
                )
            )

    return report


def project_state(
    state: dict[str, Any],
    compiled: CompiledObservation,
    *,
    actor: ActorDefinition | None = None,
    actor_view: dict[str, Any] | None = None,
    auth_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply a compiled projection to authoritative state (never returns unfiltered state)."""
    if compiled.unsupported:
        raise ObservationError(
            f"observation {compiled.projection_id!r} has unsupported semantics",
            reason_code="unsupported_observation_semantics",
        )

    if compiled.access_control is not None:
        if actor is None:
            raise ObservationError(
                f"observation {compiled.projection_id!r} requires access_control actor",
                reason_code="observation_access_denied",
            )
        decision = evaluate_authorization(
            compiled.access_control,
            actor=actor,
            actor_view=actor_view or {},
            context=auth_context,
        )
        if decision.decision is not AuthDecision.ALLOW:
            return {}

    state_copy = copy.deepcopy(state)
    if compiled.visible_paths:
        result: dict[str, Any] = {}
        for path in compiled.visible_paths:
            root = path.split(".", 1)[0]
            if root in compiled.deny_labels or path in compiled.deny_labels:
                continue
            if path in compiled.omitted_paths or root in compiled.omitted_paths:
                continue
            value = _get_path(state_copy, path)
            if value is _MISSING:
                if compiled.error_policy == "fail":
                    raise ObservationError(
                        f"visible path {path!r} missing from state",
                        reason_code="observation_path_missing",
                    )
                continue
            _set_path(result, path, copy.deepcopy(value))
    elif compiled.allow_empty_visible:
        result = state_copy
        for path in compiled.omitted_paths:
            _pop_path(result, path)
        for label in compiled.deny_labels:
            _pop_path(result, label)
    else:
        # Deny-all: no visible allow-list and not an omit-only projection.
        return {}

    for transform in compiled.transformations:
        if transform.kind == "omit":
            _pop_path(result, transform.path)
        elif transform.kind == "redact":
            if _get_path(result, transform.path) is not _MISSING:
                _set_path(result, transform.path, None)
        elif transform.kind == "rename":
            value = _get_path(result, transform.path)
            if value is _MISSING:
                continue
            _pop_path(result, transform.path)
            assert transform.rename_to is not None
            _set_path(result, transform.rename_to, value)

    return result


def observe_or_empty(
    state: dict[str, Any],
    *,
    actor: ActorDefinition,
    projections: dict[str, ObservationProjection],
    compiled_cache: dict[str, CompiledObservation] | None = None,
    actor_view: dict[str, Any] | None = None,
    auth_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fail-closed observe helper: missing/unknown/unsupported ⇒ empty dict (no full-state leak)."""
    proj_id = actor.observation_projection_id
    if not proj_id:
        return {}
    proj = projections.get(proj_id)
    if proj is None:
        return {}

    compiled: CompiledObservation | None = None
    if compiled_cache is not None and proj_id in compiled_cache:
        compiled = compiled_cache[proj_id]
    else:
        result = compile_observation(proj, strict_unsupported=True)
        if not result.ok or result.compiled is None:
            return {}
        compiled = result.compiled
        if compiled_cache is not None:
            compiled_cache[proj_id] = compiled

    try:
        return project_state(
            state,
            compiled,
            actor=actor,
            actor_view=actor_view,
            auth_context=auth_context,
        )
    except ObservationError:
        return {}


def probe_observation_leaks(
    observation: dict[str, Any],
    *,
    forbidden_paths: list[str] | tuple[str, ...] = (),
    missing_or_unknown_projection: bool = False,
) -> list[str]:
    """Return leaked path roots present in *observation*.

    Missing/unknown projection must yield an empty observation; any key is a leak.
    Otherwise report forbidden path roots (evaluator-only / omitted) that appear.
    """
    if missing_or_unknown_projection:
        return sorted(observation.keys())
    leaked: list[str] = []
    for path in forbidden_paths:
        root = path.split(".", 1)[0]
        if (root in observation or path in observation) and root not in leaked:
            leaked.append(root)
    return leaked


def _compile_transformation(raw: str) -> CompiledTransformation | None:
    text = raw.strip()
    if not text:
        return None
    rename = _RENAME_RE.match(text)
    if rename:
        return CompiledTransformation(
            kind="rename",
            path=rename.group(1).strip(),
            rename_to=rename.group(2).strip(),
        )
    redact = _REDACT_RE.match(text)
    if redact:
        path = redact.group(1).strip()
        kind: TransformationKind = "omit" if text.lower().startswith("omit:") else "redact"
        return CompiledTransformation(kind=kind, path=path)
    return None


def _get_path(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _pop_path(data: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    if len(parts) == 1:
        data.pop(parts[0], None)
        return
    cur: Any = data
    for part in parts[:-1]:
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
