"""Snapshot model for AssuredEnvironment restore/fork."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.runtime.events import Event, SideEffectIntent


class Snapshot(BaseModel):
    """Authoritative runtime checkpoint (ADR-0002)."""

    model_config = ConfigDict(extra="forbid")

    environment_id: str
    sequence: int = 0
    authoritative_state: dict[str, Any] = Field(default_factory=dict)
    actors: dict[str, Any] = Field(default_factory=dict)
    scheduled_events: list[Event] = Field(default_factory=list)
    stubs: dict[str, Any] = Field(default_factory=dict)
    clock: int = 0
    rng: dict[str, Any] = Field(default_factory=dict)
    audit_head: str = ""
    digests: dict[str, str] = Field(default_factory=dict)
    task_state: dict[str, Any] = Field(default_factory=dict)
    pending_transactions: list[dict[str, Any]] = Field(default_factory=list)
    event_log: list[Event] = Field(default_factory=list)
    recorded_intents: list[SideEffectIntent] = Field(default_factory=list)
    seed: int | None = None
    episode_id: str | None = None
