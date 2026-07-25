"""Runtime event, side-effect intent, and step result models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from envassure.runtime.outcomes import StepOutcome, outcome_is_ok


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
    # Audit / transaction metadata
    outcome: str | None = None
    reason_code: str | None = None
    transaction_id: str | None = None


class SideEffectIntent(BaseModel):
    """Declared external effect; live execution is opt-in only."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    executed: bool = False
    recorded_only: bool = True
    receipt: dict[str, Any] | None = None


class TransactionReceipt(BaseModel):
    """Atomic commit receipt for one step attempt (EAC-R05)."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str
    sequence_start: int
    sequence_end: int
    outcome: StepOutcome
    reason_code: str
    mutated_authoritative_state: bool
    event_ids: list[str] = Field(default_factory=list)
    intent_ids: list[str] = Field(default_factory=list)
    audit_head: str = ""
    state_digest: str | None = None


class StepResult(BaseModel):
    """Outcome of a single AssuredEnvironment.step call."""

    model_config = ConfigDict(extra="forbid")

    outcome: StepOutcome = StepOutcome.SUCCESS
    events: list[Event] = Field(default_factory=list)
    side_effect_intents: list[SideEffectIntent] = Field(default_factory=list)
    observation: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    terminal: bool = False
    truncated: bool = False
    failure_id: str | None = None
    failure_category: str | None = None
    reason_code: str | None = None
    info: dict[str, Any] = Field(default_factory=dict)
    state_digest: str | None = None
    transaction: TransactionReceipt | None = None
    # Legacy boolean kept for compatibility; always synced from outcome.
    ok: bool = False

    @model_validator(mode="after")
    def _sync_ok(self) -> StepResult:
        self.ok = outcome_is_ok(self.outcome)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        """Alias for outcome value (TransitionStatus)."""
        return self.outcome.value
