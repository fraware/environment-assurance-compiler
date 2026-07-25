"""Canonical JSON encoding and content digests (RFC 8785-style)."""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal
from typing import Any

__all__ = [
    "CanonicalJsonError",
    "canonical_dumps",
    "canonical_hash",
    "sha256_hex",
]


class CanonicalJsonError(ValueError):
    """Raised when a value cannot be represented in canonical JSON."""


def _encode_string(value: str) -> str:
    """Encode a JSON string with RFC 8785-compatible escaping."""
    parts: list[str] = ['"']
    for ch in value:
        code = ord(ch)
        if ch == '"':
            parts.append('\\"')
        elif ch == "\\":
            parts.append("\\\\")
        elif ch == "\b":
            parts.append("\\b")
        elif ch == "\f":
            parts.append("\\f")
        elif ch == "\n":
            parts.append("\\n")
        elif ch == "\r":
            parts.append("\\r")
        elif ch == "\t":
            parts.append("\\t")
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(ch)
    parts.append('"')
    return "".join(parts)


def _encode_number(value: int | float | Decimal) -> str:
    if isinstance(value, bool):
        # bool is a subclass of int; handled elsewhere.
        raise CanonicalJsonError("bool must not be encoded as number")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalJsonError("non-finite Decimal is not allowed")
        # Normalize to shortest form via float path only for finite values that fit.
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise CanonicalJsonError("NaN and Infinity are not allowed in canonical JSON")
        # ECMAScript NumberToJSON-style: use shortest round-trip representation.
        # Avoid '-0' asymmetry by normalizing negative zero.
        if value == 0.0:
            return "0"
        # Use format that matches common JCS: repr via format with 'g' is insufficient;
        # rely on Python's shortest round-trip for finite floats.
        text = format(value, ".17g")
        if "e" in text or "E" in text:
            # Normalize exponent sign and strip leading zeros in exponent.
            base, _, exp = text.lower().partition("e")
            sign = ""
            if exp.startswith("-"):
                sign = "-"
                exp = exp[1:]
            elif exp.startswith("+"):
                exp = exp[1:]
            exp = str(int(exp))
            return f"{base}e{sign}{exp}"
        if "." not in text and "e" not in text.lower() and value.is_integer():
            return str(int(value))
        return text
    raise CanonicalJsonError(f"unsupported number type: {type(value)!r}")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        return _encode_number(value)
    if isinstance(value, list | tuple):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        # Keys must be strings; sort by UTF-16 code units ≈ UTF-8 lexicographic for BMP.
        items: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError(f"object keys must be strings, got {type(key)!r}")
            items.append((key, item))
        items.sort(key=lambda kv: kv[0])
        inner = ",".join(_encode_string(k) + ":" + _encode(v) for k, v in items)
        return "{" + inner + "}"
    raise CanonicalJsonError(f"cannot canonicalize type {type(value)!r}")


def canonical_dumps(value: Any) -> str:
    """Serialize *value* to a canonical JSON string (no insignificant whitespace)."""
    return _encode(value)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_hash(value: Any, *, algorithm: str = "sha256") -> str:
    """Return hex digest of the canonical JSON encoding of *value*."""
    payload = canonical_dumps(value).encode("utf-8")
    if algorithm != "sha256":
        raise ValueError(f"unsupported hash algorithm: {algorithm}")
    return sha256_hex(payload)
