"""Snapshot model for AssuredEnvironment restore/fork (v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.runtime.events import Event, SideEffectIntent

SNAPSHOT_SCHEMA_VERSION = "2"


class Snapshot(BaseModel):
    """Authoritative runtime checkpoint (ADR-0002 / EAC-R07)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    environment_id: str
    world_digest: str = ""
    ir_version: str = ""
    runtime_version: str = ""
    policy_digest: str = ""
    config_digest: str = ""
    sequence: int = 0
    authoritative_state: dict[str, Any] = Field(default_factory=dict)
    actors: dict[str, Any] = Field(default_factory=dict)
    scheduled_events: list[Event] = Field(default_factory=list)
    stubs: dict[str, Any] = Field(default_factory=dict)
    clock: int = 0
    rng: dict[str, Any] = Field(default_factory=dict)
    audit_head: str = ""
    event_head: str = ""
    digests: dict[str, str] = Field(default_factory=dict)
    snapshot_digest: str = ""
    task_state: dict[str, Any] = Field(default_factory=dict)
    pending_transactions: list[dict[str, Any]] = Field(default_factory=list)
    event_log: list[Event] = Field(default_factory=list)
    recorded_intents: list[SideEffectIntent] = Field(default_factory=list)
    seed: int | None = None
    episode_id: str | None = None
    terminal: bool = False
    truncated: bool = False
