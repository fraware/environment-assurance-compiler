"""Snapshot model for AssuredEnvironment restore/fork (v2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from envassure.runtime.events import Event, SideEffectIntent, TerminalRecord
from envassure.runtime.external import SideEffectResult

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
    # Episode baseline used by ``state_from_events`` / restore reconstruct checks.
    initial_state_at_reset: dict[str, Any] = Field(default_factory=dict)
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
    side_effect_results: list[SideEffectResult] = Field(default_factory=list)
    seed: int | None = None
    episode_id: str | None = None
    terminal_record: TerminalRecord | None = None
    # Derived views of terminal_record (kept for v2 compatibility).
    terminal: bool = False
    truncated: bool = False

    @model_validator(mode="after")
    def _sync_terminal_views(self) -> Snapshot:
        if self.terminal_record is not None:
            self.terminal = self.terminal_record.terminal
            self.truncated = self.terminal_record.truncated
        return self
