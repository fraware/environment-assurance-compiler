"""Deterministic side-effect intent and transaction identifiers (EAC-03)."""

from __future__ import annotations

from typing import Any

from envassure.canonical import canonical_hash
from envassure.runtime.payloads import payload_digest, redact_payload


def canonical_effect_payload_digest(
    *,
    kind: str,
    target: str | None,
    payload: dict[str, Any],
) -> str:
    """Digest of effect kind + target + redacted payload (wall-clock free)."""
    return canonical_hash(
        {
            "kind": kind,
            "target": target,
            "payload": redact_payload(payload),
        }
    )


def make_intent_id(
    *,
    run_id: str,
    transition_index: int,
    actor_id: str,
    action_id: str,
    effect_index: int,
    canonical_effect_payload_digest: str,
) -> str:
    """Return ``sei-{hexdigest[:32]}`` for the identity tuple (never UUID/wall-clock)."""
    digest = canonical_hash(
        {
            "run_id": run_id,
            "transition_index": transition_index,
            "actor_id": actor_id,
            "action_id": action_id,
            "effect_index": effect_index,
            "canonical_effect_payload_digest": canonical_effect_payload_digest,
        }
    )
    return f"sei-{digest[:32]}"


def make_transaction_id(*, run_id: str, transition_index: int) -> str:
    """Stabilize transaction ids from ``(run_id, transition_index)``."""
    digest = canonical_hash(
        {
            "run_id": run_id,
            "transition_index": transition_index,
        }
    )
    return f"tx-{digest[:32]}"


def seed_derived_episode_id(seed: int) -> str:
    """Seed-stable run id when callers omit ``options.episode_id``."""
    return f"ep-seed-{seed}"


__all__ = [
    "canonical_effect_payload_digest",
    "make_intent_id",
    "make_transaction_id",
    "payload_digest",
    "seed_derived_episode_id",
]
