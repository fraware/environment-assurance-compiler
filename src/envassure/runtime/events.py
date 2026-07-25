"""Runtime event, side-effect intent, and step result models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    """Immutable fact recorded by the event-sourced runtime."""

    model_config = ConfigDict(extra="forbid")

    id: str
    type: str
    sequence: int
    clock: int
    actor_id: str | None = None
    action_id: str | None = None
    branch_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    writes: dict[str, Any] = Field(default_factory=dict)


class SideEffectIntent(BaseModel):
    """Declared external effect; live execution is opt-in only."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    executed: bool = False
    recorded_only: bool = True


class StepResult(BaseModel):
    """Outcome of a single AssuredEnvironment.step call."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    events: list[Event] = Field(default_factory=list)
    side_effect_intents: list[SideEffectIntent] = Field(default_factory=list)
    observation: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    terminal: bool = False
    truncated: bool = False
    failure_id: str | None = None
    failure_category: str | None = None
    info: dict[str, Any] = Field(default_factory=dict)
    state_digest: str | None = None
