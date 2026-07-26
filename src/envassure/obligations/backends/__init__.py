"""Obligation backends (OPA / Rego)."""

from __future__ import annotations

from envassure.obligations.backends.opa import (
    OPA_FAMILIES,
    OpaBackendError,
    emit_rego_v1_bundle,
    opa_eval,
    opa_fmt_check,
    opa_test,
    require_opa_binary,
)

__all__ = [
    "OPA_FAMILIES",
    "OpaBackendError",
    "emit_rego_v1_bundle",
    "opa_eval",
    "opa_fmt_check",
    "opa_test",
    "require_opa_binary",
]
