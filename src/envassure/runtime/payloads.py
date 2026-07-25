"""Action payload schema validation and redaction (EAC-R02)."""

from __future__ import annotations

from typing import Any

from envassure.canonical import canonical_hash


class PayloadValidationError(ValueError):
    """Raised when an action payload fails its compiled input_schema."""

    def __init__(self, message: str, *, path: str = "", reason_code: str = "invalid_input") -> None:
        super().__init__(message)
        self.path = path
        self.reason_code = reason_code


# Field names (case-insensitive) redacted in event/audit payloads by default.
DEFAULT_REDACT_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "auth",
        "credential",
        "credentials",
        "private_key",
        "ssn",
        "credit_card",
        "card_number",
    }
)

REDACTED = "***REDACTED***"


def validate_payload(schema: dict[str, Any], payload: dict[str, Any]) -> None:
    """Validate *payload* against a JSON-Schema-like *schema* (fail closed).

    Supports a pragmatic subset: ``type``, ``required``, ``properties``,
    ``additionalProperties``, ``enum``, ``minimum``/``maximum``, ``minLength``/
    ``maxLength``, ``items``. Empty schema accepts any object payload.
    """
    if not schema:
        if not isinstance(payload, dict):
            raise PayloadValidationError("payload must be an object", reason_code="invalid_input")
        return
    _validate_node(schema, payload, path="$")


def _validate_node(schema: dict[str, Any], value: Any, *, path: str) -> None:
    expected = schema.get("type")
    if expected is not None:
        if not _type_matches(expected, value):
            raise PayloadValidationError(
                f"{path}: expected type {expected!r}, got {type(value).__name__}",
                path=path,
            )

    if "enum" in schema:
        if value not in schema["enum"]:
            raise PayloadValidationError(
                f"{path}: value {value!r} not in enum {schema['enum']!r}",
                path=path,
            )

    if isinstance(value, int | float) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise PayloadValidationError(f"{path}: {value} < minimum {schema['minimum']}", path=path)
        if "maximum" in schema and value > schema["maximum"]:
            raise PayloadValidationError(f"{path}: {value} > maximum {schema['maximum']}", path=path)

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise PayloadValidationError(
                f"{path}: string shorter than minLength {schema['minLength']}",
                path=path,
            )
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise PayloadValidationError(
                f"{path}: string longer than maxLength {schema['maxLength']}",
                path=path,
            )

    if isinstance(value, list) and "items" in schema:
        item_schema = schema["items"]
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                _validate_node(item_schema, item, path=f"{path}[{idx}]")

    if isinstance(value, dict) and (
        expected == "object" or "properties" in schema or "required" in schema
    ):
        required = schema.get("required") or []
        for key in required:
            if key not in value:
                raise PayloadValidationError(
                    f"{path}: missing required property {key!r}",
                    path=f"{path}.{key}",
                )
        properties = schema.get("properties") or {}
        additional = schema.get("additionalProperties", True)
        for key, child in value.items():
            if key in properties:
                _validate_node(properties[key], child, path=f"{path}.{key}")
            elif additional is False:
                raise PayloadValidationError(
                    f"{path}: additional property {key!r} not allowed",
                    path=f"{path}.{key}",
                )
            elif isinstance(additional, dict):
                _validate_node(additional, child, path=f"{path}.{key}")


def _type_matches(expected: str | list[str], value: Any) -> bool:
    if isinstance(expected, list):
        return any(_type_matches(item, value) for item in expected)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    # Unknown type names fail closed.
    return False


def redact_payload(
    payload: dict[str, Any],
    *,
    redact_keys: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Return a deep-copied payload with sensitive keys replaced."""
    keys = redact_keys if redact_keys is not None else DEFAULT_REDACT_KEYS
    return _redact(payload, keys)  # type: ignore[return-value]


def _redact(value: Any, keys: frozenset[str]) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in keys:
                out[k] = REDACTED
            else:
                out[k] = _redact(v, keys)
        return out
    if isinstance(value, list):
        return [_redact(item, keys) for item in value]
    return value


def payload_digest(payload: dict[str, Any]) -> str:
    """Canonical digest of a (typically redacted) payload."""
    return canonical_hash(payload)
