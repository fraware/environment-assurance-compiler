"""Ordered IR document transforms between supported minor versions.

Transforms mutate raw JSON payloads only. They are applied exclusively by
``eac migrate`` — never by lint, verify-pack, or load paths.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from envassure.ir.primitives import IR_PRIOR_STABLE, IR_VERSION

TransformFn = Callable[[dict[str, Any]], dict[str, Any]]


def transform_0_1_0_to_0_2_0(payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a 0.1.0 world document to 0.2.0.

    Documented schema delta
    -----------------------
    * **Additive:** ``assurance_profile`` (default ``"baseline"``).
    * **Normalized default:** ``state_model_version`` ``"1"`` → ``"1.0"``.
    * **Optional rename:** deprecated top-level ``profile`` (if present) is
      copied into ``assurance_profile`` and removed.

    Note: ``ProvenanceRef.origin_kind`` is additive on the write-current 0.2.0
    schema and does not require a cross-minor transform (absent → ``null``).
    """
    out = dict(payload)
    notes: list[str] = []

    # Optional rename: experimental/draft ``profile`` → ``assurance_profile``.
    if "profile" in out and "assurance_profile" not in out:
        profile_val = out.pop("profile")
        if isinstance(profile_val, str) and profile_val:
            out["assurance_profile"] = profile_val
            notes.append("renamed profile -> assurance_profile")
        else:
            notes.append("dropped empty deprecated profile field")
    elif "profile" in out:
        out.pop("profile")
        notes.append("removed deprecated profile (assurance_profile already set)")

    if "assurance_profile" not in out or out["assurance_profile"] in (None, ""):
        out["assurance_profile"] = "baseline"
        notes.append("set assurance_profile=baseline")

    smv = out.get("state_model_version")
    if smv is None or smv == "1":
        out["state_model_version"] = "1.0"
        notes.append("normalized state_model_version 1 -> 1.0")

    out["ir_version"] = IR_VERSION
    out["_migrate_notes"] = notes
    return out


# Ordered edges: (from_version, to_version, transform).
TRANSFORM_GRAPH: list[tuple[str, str, TransformFn]] = [
    (IR_PRIOR_STABLE, IR_VERSION, transform_0_1_0_to_0_2_0),
]


def identity_transform(payload: dict[str, Any]) -> dict[str, Any]:
    """No-op transform for same-version migrate."""
    return dict(payload)


def migration_path(from_version: str, to_version: str) -> list[tuple[str, str, TransformFn]]:
    """Return ordered transforms from ``from_version`` to ``to_version``.

    Raises:
        KeyError: no path exists between the versions.
    """
    if from_version == to_version:
        return []
    # Linear chain for the two-minor window; extend with BFS when needed.
    path: list[tuple[str, str, TransformFn]] = []
    current = from_version
    remaining = list(TRANSFORM_GRAPH)
    guard = 0
    while current != to_version:
        guard += 1
        if guard > len(TRANSFORM_GRAPH) + 1:
            raise KeyError(f"no migration path from {from_version} to {to_version}")
        edge = next((e for e in remaining if e[0] == current), None)
        if edge is None:
            raise KeyError(f"no migration path from {from_version} to {to_version}")
        remaining.remove(edge)
        path.append(edge)
        current = edge[1]
    return path


def apply_transforms(
    payload: dict[str, Any],
    from_version: str,
    to_version: str,
) -> tuple[dict[str, Any], list[str]]:
    """Apply the ordered transform chain; return ``(payload, notes)``."""
    if from_version == to_version:
        return identity_transform(payload), ["identity; already at target version"]
    path = migration_path(from_version, to_version)
    current = dict(payload)
    all_notes: list[str] = []
    for src, dst, fn in path:
        current = fn(current)
        step_notes = current.pop("_migrate_notes", None)
        if isinstance(step_notes, list):
            all_notes.extend(f"{src}->{dst}: {n}" for n in step_notes)
        else:
            all_notes.append(f"applied {src}->{dst}")
        current["ir_version"] = dst
    return current, all_notes
