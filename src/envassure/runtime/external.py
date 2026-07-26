"""External effect executor protocol and receipts (EAC-R06)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash
from envassure.runtime.events import SideEffectIntent

EffectStatus = Literal[
    "recorded",
    "executed",
    "failed",
    "skipped",
    "compensated",
]


class SideEffectResult(BaseModel):
    """Immutable result for one external-effect attempt (authoritative public name)."""

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    intent_digest: str
    executor_id: str
    executor_version: str
    attempt: int = 1
    idempotency_key: str
    started_at: str
    finished_at: str
    status: EffectStatus
    response_digest: str | None = None
    error: str | None = None
    compensation: dict[str, Any] | None = None
    details: dict[str, Any] = Field(default_factory=dict)


# Backward-compatible alias for one release (prefer SideEffectResult).
EffectReceipt = SideEffectResult


@runtime_checkable
class ExternalEffectExecutor(Protocol):
    """Injected boundary for live external effects (never fabricated)."""

    @property
    def executor_id(self) -> str: ...

    @property
    def executor_version(self) -> str: ...

    def execute(
        self,
        intent: SideEffectIntent,
        *,
        attempt: int = 1,
        idempotency_key: str | None = None,
    ) -> SideEffectResult:
        """Execute or reject *intent*; must return a typed receipt."""
        ...


def intent_digest(intent: SideEffectIntent) -> str:
    return canonical_hash(
        {
            "id": intent.id,
            "kind": intent.kind,
            "target": intent.target,
            "payload": intent.payload,
        }
    )


def recorded_receipt(
    intent: SideEffectIntent,
    *,
    attempt: int = 1,
) -> SideEffectResult:
    """Default record-only receipt (no live execution claimed)."""
    now = datetime.now(UTC).isoformat()
    digest = intent_digest(intent)
    return SideEffectResult(
        intent_id=intent.id,
        intent_digest=digest,
        executor_id="record-only",
        executor_version="1",
        attempt=attempt,
        idempotency_key=intent.id,
        started_at=now,
        finished_at=now,
        status="recorded",
        response_digest=None,
    )


class RejectingExecutor:
    """Fail-closed executor used when live mode is requested without a real executor."""

    executor_id = "rejecting"
    executor_version = "1"

    def execute(
        self,
        intent: SideEffectIntent,
        *,
        attempt: int = 1,
        idempotency_key: str | None = None,
    ) -> SideEffectResult:
        now = datetime.now(UTC).isoformat()
        return SideEffectResult(
            intent_id=intent.id,
            intent_digest=intent_digest(intent),
            executor_id=self.executor_id,
            executor_version=self.executor_version,
            attempt=attempt,
            idempotency_key=idempotency_key or intent.id,
            started_at=now,
            finished_at=now,
            status="failed",
            error="live_external_effects requires an injected ExternalEffectExecutor",
        )
