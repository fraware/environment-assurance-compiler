"""AssuredEnvironment protocol (framework-agnostic runtime surface)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from envassure.runtime.events import StepResult
from envassure.runtime.snapshot import Snapshot


@runtime_checkable
class AssuredEnvironment(Protocol):
    """Native EnvAssure runtime contract (ADR-0001 / ADR-0002)."""

    def reset(
        self,
        *,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reset episode state; return initial observation for the default actor."""
        ...

    def step(
        self,
        actor_id: str,
        action_id: str,
        payload: dict[str, Any] | None = None,
    ) -> StepResult:
        """Validate and apply one action; return events, observation, and status."""
        ...

    def state(self) -> dict[str, Any]:
        """Return a copy of authoritative state (never a live mutable alias)."""
        ...

    def observe(self, actor_id: str) -> dict[str, Any]:
        """Project authoritative state for *actor_id*."""
        ...

    def snapshot(self) -> Snapshot:
        """Capture a restoreable checkpoint."""
        ...

    def restore(self, snapshot: Snapshot) -> None:
        """Replace runtime state from *snapshot*."""
        ...

    def fork(self) -> AssuredEnvironment:
        """Return an independent copy at the current snapshot."""
        ...
