"""Shared helpers for optional Gymnasium / PettingZoo adapters (EAC-09)."""

from __future__ import annotations

from typing import Any, Literal

from envassure.canonical import canonical_hash
from envassure.expressions.parser import coerce_literal
from envassure.ir.models import (
    ActorDefinition,
    ObservationProjection,
    StateVariable,
    WorldDefinition,
)
from envassure.ir.primitives import StateTypeName
from envassure.runtime.authorization import AuthDecision, evaluate_authorization
from envassure.runtime.events import StepResult, TerminalRecord
from envassure.runtime.observations import compile_observation
from envassure.runtime.protocol import AssuredEnvironment

# State types with a direct Gymnasium space mapping (lossy codecs declared below).
_SUPPORTED_SPACE_TYPES: frozenset[str] = frozenset(
    {
        "scalar",
        "enum",
        "resource_counter",
        "timestamp",
        "duration",
        "record",
        "list",
    }
)

# Fail closed without an explicit codec plugin.
_UNSUPPORTED_WITHOUT_CODEC: frozenset[str] = frozenset(
    {
        "map",
        "graph",
        "opaque_external_ref",
        "set",
    }
)

_TEXT_MAX_LENGTH = 1024
_LIST_MAX_LENGTH = 64
_LOSSY_CODECS: frozenset[str] = frozenset({"record.json_text", "list.json_text"})
ScalarSpaceKind = Literal["box", "text"]


class AdapterSemanticsError(ValueError):
    """Fail-closed adapter configuration / IR mapping error."""


def require_world(env: AssuredEnvironment) -> WorldDefinition:
    """Return the IR world bound to *env* (fail closed if unavailable)."""
    world = getattr(env, "world", None)
    if world is None:
        world = getattr(env, "_world", None)
    if not isinstance(world, WorldDefinition):
        raise AdapterSemanticsError(
            "AssuredEnvironment must expose a WorldDefinition via .world for adapters"
        )
    return world


def terminal_record_of(env: AssuredEnvironment) -> TerminalRecord | None:
    record = getattr(env, "terminal_record", None)
    if record is None:
        record = getattr(env, "_terminal_record", None)
    if isinstance(record, TerminalRecord):
        return record
    return None


def episode_termination_flags(
    result: StepResult,
    env: AssuredEnvironment,
) -> tuple[bool, bool]:
    """Map ``(terminated, truncated)`` from TerminalRecord when present, else StepResult.

    Gymnasium / PettingZoo convention: ``terminated`` is a natural episode end;
    ``truncated`` is a time-limit / horizon cut. When truncated, ``terminated`` is
    False even if the durable record marks ``terminal=True``.
    """
    record = terminal_record_of(env)
    if record is not None and (result.terminal or result.truncated or record.terminal):
        truncated = bool(record.truncated)
        terminated = bool(record.terminal) and not truncated
        return terminated, truncated
    truncated = bool(result.truncated)
    terminated = bool(result.terminal) and not truncated
    return terminated, truncated


def _actor_view(env: AssuredEnvironment, actor: ActorDefinition) -> dict[str, Any]:
    runtime = getattr(env, "_actor_runtime", None)
    if isinstance(runtime, dict):
        view = runtime.get(actor.id)
        if isinstance(view, dict):
            return view
    return {
        "id": actor.id,
        "actor_class": actor.actor_class,
        "roles": list(actor.roles),
        "capabilities": list(actor.capabilities),
        "credentials": list(actor.credentials),
        "available_actions": list(actor.available_actions),
        "observation_projection_id": actor.observation_projection_id,
        "revocation_rules": list(actor.revocation_rules),
        "delegation_rules": list(actor.delegation_rules),
        "authority_source": actor.authority_source,
    }


def _auth_context(env: AssuredEnvironment) -> dict[str, Any]:
    ctx = getattr(env, "_auth_context", None)
    return dict(ctx) if isinstance(ctx, dict) else {}


def legal_action_ids(env: AssuredEnvironment, actor_id: str) -> list[str]:
    """Actions available to *actor_id* that pass actor-class + authorization checks."""
    world = require_world(env)
    actors = world.index_actors()
    actor = actors.get(actor_id)
    if actor is None:
        raise AdapterSemanticsError(f"unknown actor {actor_id!r}")
    actions = world.index_actions()
    actor_view = _actor_view(env, actor)
    context = {**_auth_context(env), "payload": {}, "clock": getattr(env, "_clock", 0)}
    legal: list[str] = []
    for action_id in actor.available_actions:
        action = actions.get(action_id)
        if action is None:
            continue
        if action.actor_classes and actor.actor_class not in action.actor_classes:
            continue
        if action.authorization:
            result = evaluate_authorization(
                action.authorization,
                actor=actor,
                actor_view=actor_view,
                context=context,
            )
            if result.decision is not AuthDecision.ALLOW:
                continue
        legal.append(action_id)
    return legal


def action_mask(action_ids: list[str], legal: list[str]) -> list[bool]:
    legal_set = set(legal)
    return [aid in legal_set for aid in action_ids]


def evidence_digests(
    env: AssuredEnvironment,
    *,
    observation: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Canonical digests for adapter ``info`` evidence (state / observation / world)."""
    digests: dict[str, str] = {}
    try:
        digests["state_digest"] = canonical_hash(env.state())
    except Exception:  # pragma: no cover - defensive
        digests["state_digest"] = ""
    if observation is not None:
        digests["observation_digest"] = canonical_hash(observation)
    world = getattr(env, "world", None) or getattr(env, "_world", None)
    if isinstance(world, WorldDefinition):
        digests["world_digest"] = canonical_hash(world.content_dict())
    return digests


def step_info(
    result: StepResult,
    *,
    actor_id: str,
    action_ids: list[str],
    legal: list[str],
    extra: dict[str, Any] | None = None,
    env: AssuredEnvironment | None = None,
    observation: dict[str, Any] | None = None,
    reward_status: str | None = None,
) -> dict[str, Any]:
    """Build adapter ``info`` with required outcome fields + legal-action masks."""
    info: dict[str, Any] = {
        **result.info,
        "actor_id": actor_id,
        "ok": result.ok,
        "outcome": result.outcome.value,
        "reason_code": result.reason_code,
        "failure_id": result.failure_id,
        "legal_actions": list(legal),
        "action_masks": action_mask(action_ids, legal),
        "lossy_codecs": sorted(_LOSSY_CODECS),
    }
    if reward_status is not None:
        info["reward_status"] = reward_status
    if env is not None:
        info.update(evidence_digests(env, observation=observation))
    if extra:
        info.update(extra)
    return info


def _is_numeric_literal(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int | float):
        return True
    if isinstance(value, str):
        try:
            float(value.strip())
        except ValueError:
            return False
        return True
    return False


def scalar_space_kind(var: StateVariable) -> ScalarSpaceKind:
    """Choose Box vs Text for scalar-family IR types (adapter boundary only).

    Numeric ``initial_generator`` values (and all timestamp/duration) map to Box.
    Uninitialized or non-numeric scalars map to Text so string identities stay
    ``space.contains``-compatible after encode.
    """
    if var.type in {"timestamp", "duration"}:
        return "box"
    if var.type != "scalar":
        raise AdapterSemanticsError(f"scalar_space_kind expected scalar-family, got {var.type!r}")
    if var.initial_generator is None:
        return "text"
    lit = coerce_literal(var.initial_generator)
    return "box" if _is_numeric_literal(lit) else "text"


def _space_for_state_variable(gym: Any, var: StateVariable) -> Any:
    import numpy as np

    state_type: StateTypeName = var.type
    if state_type in _UNSUPPORTED_WITHOUT_CODEC:
        raise AdapterSemanticsError(
            f"state type {state_type!r} requires a codec plugin (fail closed)"
        )
    if state_type == "enum":
        if not var.enum_values:
            raise AdapterSemanticsError("enum state variable requires enum_values for spaces")
        return gym.spaces.Discrete(len(var.enum_values))
    if state_type == "resource_counter":
        return gym.spaces.Box(
            low=0,
            high=np.iinfo(np.int64).max,
            shape=(),
            dtype=np.int64,
        )
    if state_type in {"scalar", "timestamp", "duration"}:
        if scalar_space_kind(var) == "text":
            return gym.spaces.Text(max_length=_TEXT_MAX_LENGTH, min_length=0)
        return gym.spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(),
            dtype=np.float64,
        )
    if state_type in {"record", "list"}:
        # Lossy JSON-text codec: structure preserved as Text for space.contains.
        return gym.spaces.Text(max_length=_TEXT_MAX_LENGTH, min_length=0)
    raise AdapterSemanticsError(f"unsupported state type for observation space: {state_type!r}")


def _visible_state_vars_for_projection(
    world: WorldDefinition,
    proj: ObservationProjection,
) -> dict[str, StateVariable]:
    compiled = compile_observation(proj, strict_unsupported=True)
    if not compiled.ok or compiled.compiled is None:
        reasons = "; ".join(compiled.unsupported) or f"observation {proj.id!r} failed to compile"
        raise AdapterSemanticsError(reasons)
    if compiled.compiled.unsupported:
        raise AdapterSemanticsError(
            f"observation {proj.id!r} has unsupported semantics: "
            + "; ".join(compiled.compiled.unsupported)
        )
    if not compiled.compiled.visible_paths:
        raise AdapterSemanticsError(
            f"observation {proj.id!r} has no visible_paths; cannot build observation space"
        )

    state_index = world.index_state()
    vars_by_path: dict[str, StateVariable] = {}
    for path in compiled.compiled.visible_paths:
        if "." in path:
            raise AdapterSemanticsError(
                f"observation {proj.id!r} nested path {path!r} is unsupported for spaces"
            )
        if path in compiled.compiled.omitted_paths:
            continue
        var = state_index.get(path)
        if var is None:
            raise AdapterSemanticsError(
                f"observation {proj.id!r} visible path {path!r} is not a declared state variable"
            )
        if var.type not in _SUPPORTED_SPACE_TYPES:
            raise AdapterSemanticsError(
                f"observation {proj.id!r} path {path!r} has unsupported type {var.type!r}"
            )
        vars_by_path[path] = var
    if not vars_by_path:
        raise AdapterSemanticsError(
            f"observation {proj.id!r} produced an empty observation space (fail closed)"
        )
    return vars_by_path


def _projection_for_actor(world: WorldDefinition, actor_id: str) -> ObservationProjection | None:
    actors = world.index_actors()
    actor = actors.get(actor_id)
    if actor is None:
        raise AdapterSemanticsError(f"unknown actor {actor_id!r}")
    proj_id = actor.observation_projection_id
    if not proj_id:
        return None
    projections = {o.id: o for o in world.observations}
    proj = projections.get(proj_id)
    if proj is None:
        raise AdapterSemanticsError(
            f"actor {actor_id!r} references unknown observation projection {proj_id!r}"
        )
    return proj


def encode_observation_value(var: StateVariable, value: Any) -> Any:
    """Map an IR-native observation leaf to a Gymnasium space sample."""
    import json

    import numpy as np

    if var.type == "enum":
        labels = list(var.enum_values or [])
        if not labels:
            raise AdapterSemanticsError(f"enum state {var.id!r} has no enum_values")
        if not isinstance(value, str):
            raise AdapterSemanticsError(
                f"enum state {var.id!r} expected string label, got {type(value).__name__}"
            )
        try:
            return int(labels.index(value))
        except ValueError as exc:
            raise AdapterSemanticsError(
                f"enum state {var.id!r} value {value!r} not in enum_values {labels}"
            ) from exc
    if var.type == "resource_counter":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise AdapterSemanticsError(
                f"resource_counter {var.id!r} expected int, got {type(value).__name__}"
            )
        # 0-d ndarray avoids Gymnasium Box.contains cast warnings under -Werror.
        return np.asarray(int(value), dtype=np.int64)
    if var.type in {"scalar", "timestamp", "duration"}:
        if scalar_space_kind(var) == "text":
            if value is None:
                return ""
            if not isinstance(value, str):
                raise AdapterSemanticsError(
                    f"text scalar {var.id!r} expected str|None, got {type(value).__name__}"
                )
            if len(value) > _TEXT_MAX_LENGTH:
                raise AdapterSemanticsError(
                    f"text scalar {var.id!r} exceeds max_length {_TEXT_MAX_LENGTH}"
                )
            return value
        if value is None:
            return np.asarray(np.nan, dtype=np.float64)
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise AdapterSemanticsError(
                f"numeric scalar {var.id!r} expected number, got {type(value).__name__}"
            )
        return np.asarray(float(value), dtype=np.float64)
    if var.type in {"record", "list"}:
        if value is None:
            text = ""
        elif isinstance(value, str):
            text = value
        else:
            text = json.dumps(value, separators=(",", ":"), sort_keys=True)
        if len(text) > _TEXT_MAX_LENGTH:
            raise AdapterSemanticsError(
                f"{var.type} {var.id!r} JSON encoding exceeds max_length {_TEXT_MAX_LENGTH}"
            )
        return text
    if var.type in _UNSUPPORTED_WITHOUT_CODEC:
        raise AdapterSemanticsError(
            f"state type {var.type!r} requires a codec plugin (fail closed)"
        )
    raise AdapterSemanticsError(f"unsupported encode type {var.type!r} for {var.id!r}")


def decode_observation_value(var: StateVariable, encoded: Any) -> Any:
    """Inverse of :func:`encode_observation_value` (debug / human APIs)."""
    import json

    import numpy as np

    if var.type == "enum":
        labels = list(var.enum_values or [])
        idx = int(encoded)
        if idx < 0 or idx >= len(labels):
            raise AdapterSemanticsError(f"enum index {idx} out of range for {var.id!r}")
        return labels[idx]
    if var.type == "resource_counter":
        return int(encoded)
    if var.type in {"scalar", "timestamp", "duration"}:
        if scalar_space_kind(var) == "text":
            text = str(encoded)
            return None if text == "" else text
        num = float(encoded)
        if isinstance(encoded, float | np.floating) and np.isnan(num):
            return None
        return num
    if var.type in {"record", "list"}:
        text = str(encoded)
        if text == "":
            return {} if var.type == "record" else []
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise AdapterSemanticsError(
                f"failed to decode {var.type} {var.id!r} from Text codec"
            ) from exc
    raise AdapterSemanticsError(f"unsupported decode type {var.type!r} for {var.id!r}")


def encode_observation(
    world: WorldDefinition,
    actor_id: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    """Encode an IR-native observation dict into Gymnasium space samples."""
    proj = _projection_for_actor(world, actor_id)
    if proj is None:
        if observation:
            raise AdapterSemanticsError(
                f"actor {actor_id!r} has no observation projection but observation is non-empty"
            )
        return {}
    vars_by_path = _visible_state_vars_for_projection(world, proj)
    encoded: dict[str, Any] = {}
    for path, var in vars_by_path.items():
        if path not in observation:
            raise AdapterSemanticsError(
                f"observation for actor {actor_id!r} missing required path {path!r}"
            )
        encoded[path] = encode_observation_value(var, observation[path])
    extra = set(observation) - set(vars_by_path)
    if extra:
        raise AdapterSemanticsError(
            f"observation for actor {actor_id!r} has unexpected paths: {sorted(extra)}"
        )
    return encoded


def decode_observation(
    world: WorldDefinition,
    actor_id: str,
    encoded: dict[str, Any],
) -> dict[str, Any]:
    """Decode Gymnasium observation samples back to IR-native values."""
    proj = _projection_for_actor(world, actor_id)
    if proj is None:
        return {}
    vars_by_path = _visible_state_vars_for_projection(world, proj)
    decoded: dict[str, Any] = {}
    for path, var in vars_by_path.items():
        if path not in encoded:
            raise AdapterSemanticsError(
                f"encoded observation for actor {actor_id!r} missing path {path!r}"
            )
        decoded[path] = decode_observation_value(var, encoded[path])
    return decoded


def observation_space_for_actor(
    gym: Any,
    world: WorldDefinition,
    actor_id: str,
) -> Any:
    """Build a Gymnasium Dict observation space from the actor's IR projection.

    Fail closed when the projection is missing unsupported semantics, nested paths,
    or state types without a space mapping. Enum leaves are Discrete; adapters must
    encode string labels via :func:`encode_observation` before returning observations.
    """
    proj = _projection_for_actor(world, actor_id)
    if proj is None:
        return gym.spaces.Dict({})
    return observation_space_for_projection(gym, world, proj)


def observation_space_for_projection(
    gym: Any,
    world: WorldDefinition,
    proj: ObservationProjection,
) -> Any:
    vars_by_path = _visible_state_vars_for_projection(world, proj)
    spaces = {path: _space_for_state_variable(gym, var) for path, var in vars_by_path.items()}
    return gym.spaces.Dict(spaces)


def resolve_action_ids(
    world: WorldDefinition,
    actor_id: str,
    action_ids: list[str] | None,
) -> list[str]:
    """Caller-supplied action ids, or the actor's IR ``available_actions``."""
    if action_ids:
        return list(action_ids)
    actors = world.index_actors()
    actor = actors.get(actor_id)
    if actor is None:
        raise AdapterSemanticsError(f"unknown actor {actor_id!r}")
    if not actor.available_actions:
        raise AdapterSemanticsError(f"actor {actor_id!r} has no available_actions")
    return list(actor.available_actions)


def _actions_need_payload_dict(world: WorldDefinition, action_ids: list[str]) -> bool:
    index = world.index_actions()
    for aid in action_ids:
        action = index.get(aid)
        if action is None:
            continue
        schema = action.input_schema or {}
        if schema.get("properties") or schema.get("required"):
            return True
    return False


def _json_schema_to_space(gym: Any, schema: dict[str, Any], *, path: str) -> Any:
    """Map a JSON-Schema-like fragment to a Gymnasium space (fail closed)."""
    import numpy as np

    stype = schema.get("type")
    if "enum" in schema and isinstance(schema["enum"], list):
        return gym.spaces.Discrete(len(schema["enum"]))
    if stype == "integer" or stype == "number":
        low = schema.get("minimum", -np.inf if stype == "number" else np.iinfo(np.int64).min)
        high = schema.get("maximum", np.inf if stype == "number" else np.iinfo(np.int64).max)
        dtype = np.float64 if stype == "number" else np.int64
        return gym.spaces.Box(low=low, high=high, shape=(), dtype=dtype)
    if stype == "boolean":
        return gym.spaces.Discrete(2)
    if stype == "string":
        max_len = int(schema.get("maxLength") or _TEXT_MAX_LENGTH)
        min_len = int(schema.get("minLength") or 0)
        return gym.spaces.Text(max_length=max_len, min_length=min_len)
    if stype == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        if not isinstance(props, dict) or not props:
            return gym.spaces.Dict({})
        spaces = {
            key: _json_schema_to_space(gym, sub if isinstance(sub, dict) else {}, path=f"{path}.{key}")
            for key, sub in props.items()
        }
        return gym.spaces.Dict(spaces)
    if stype == "array":
        # Lossy: encode arrays as JSON Text (bounded).
        return gym.spaces.Text(max_length=_TEXT_MAX_LENGTH, min_length=0)
    if stype is None and not schema:
        return gym.spaces.Dict({})
    raise AdapterSemanticsError(f"unsupported payload schema at {path}: {schema!r}")


def _merged_payload_schema(world: WorldDefinition, action_ids: list[str]) -> dict[str, Any]:
    """Union of action input_schema properties (optional fields for Dict action space)."""
    index = world.index_actions()
    properties: dict[str, Any] = {}
    for aid in action_ids:
        action = index.get(aid)
        if action is None:
            continue
        schema = action.input_schema or {}
        props = schema.get("properties") or {}
        if not isinstance(props, dict):
            continue
        for key, sub in props.items():
            if key not in properties and isinstance(sub, dict):
                properties[key] = sub
    return {"type": "object", "properties": properties, "additionalProperties": False}


def action_space_for_actor(
    gym: Any,
    world: WorldDefinition,
    actor_id: str,
    action_ids: list[str] | None = None,
) -> Any:
    """Build Discrete or Dict action space (payload-bearing actions use Dict)."""
    resolved = resolve_action_ids(world, actor_id, action_ids)
    if not resolved:
        raise AdapterSemanticsError(f"actor {actor_id!r} has empty action space")
    discrete = gym.spaces.Discrete(len(resolved))
    if not _actions_need_payload_dict(world, resolved):
        return discrete
    payload_schema = _merged_payload_schema(world, resolved)
    payload_space = _json_schema_to_space(gym, payload_schema, path="payload")
    return gym.spaces.Dict({"action_id": discrete, "payload": payload_space})


def decode_action(
    action: Any,
    *,
    action_ids: list[str],
    action_space: Any,
) -> tuple[str, dict[str, Any]]:
    """Decode a Gymnasium action sample into ``(action_id, payload)``."""
    # Discrete index or bare string action id.
    if isinstance(action, str):
        return action, {}
    if isinstance(action, int | float):
        idx = int(action)
        if idx < 0 or idx >= len(action_ids):
            raise AdapterSemanticsError(f"action index {idx} out of range")
        return action_ids[idx], {}
    if isinstance(action, dict):
        raw_id = action.get("action_id", action.get("action"))
        payload = action.get("payload")
        if payload is None:
            payload = {k: v for k, v in action.items() if k not in {"action_id", "action"}}
        if not isinstance(payload, dict):
            raise AdapterSemanticsError("action payload must be a dict")
        # Normalize nested Dict samples (Gymnasium may emit numpy scalars).
        try:
            import numpy as np

            if isinstance(raw_id, np.integer | np.floating):
                raw_id = int(raw_id)
            elif isinstance(raw_id, np.ndarray) and raw_id.shape == ():
                raw_id = raw_id.item()
            payload = {
                key: (val.item() if isinstance(val, np.generic) else val)
                for key, val in payload.items()
            }
        except ImportError:  # pragma: no cover
            pass
        if isinstance(raw_id, str):
            return raw_id, dict(payload)
        if isinstance(raw_id, int | float):
            idx = int(raw_id)
            if idx < 0 or idx >= len(action_ids):
                raise AdapterSemanticsError(f"action index {idx} out of range")
            return action_ids[idx], dict(payload)
        raise AdapterSemanticsError("Dict action requires action_id (int or str)")
    # Numpy 0-d integer
    try:
        import numpy as np

        if isinstance(action, np.integer | np.floating):
            return decode_action(int(action), action_ids=action_ids, action_space=action_space)
        if isinstance(action, np.ndarray) and action.shape == ():
            return decode_action(action.item(), action_ids=action_ids, action_space=action_space)
    except ImportError:  # pragma: no cover
        pass
    raise AdapterSemanticsError(f"malformed action of type {type(action).__name__}")


def declared_lossy_codecs() -> frozenset[str]:
    """Codecs that intentionally lose structure at the adapter boundary."""
    return _LOSSY_CODECS
