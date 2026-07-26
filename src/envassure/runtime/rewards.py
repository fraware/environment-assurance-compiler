"""RewardProvider protocol shared by Gymnasium and OpenEnv adapters."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from envassure.runtime.events import StepResult

REWARD_STATUS_UNCONFIGURED = "unconfigured"
REWARD_STATUS_CONFIGURED = "configured"


@runtime_checkable
class RewardProvider(Protocol):
    """Compute a scalar reward from a step result.

    Adapters must not invent domain rewards. When no provider is supplied,
    use :class:`NeutralRewardProvider` and set ``reward_status="unconfigured"``.
    """

    def reward(
        self,
        result: StepResult,
        *,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> float:
        """Return the scalar reward for *result*."""
        ...


class NeutralRewardProvider:
    """Always returns ``0.0`` — the fail-closed default when rewards are absent."""

    def reward(
        self,
        result: StepResult,
        *,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> float:
        return 0.0


class OutcomeRewardProvider:
    """Simple outcome-shaped reward: ``+1`` on success, ``-1`` otherwise.

    Explicitly opt-in; never the adapter default (avoids claiming a domain reward).
    """

    def reward(
        self,
        result: StepResult,
        *,
        actor_id: str,
        context: dict[str, Any] | None = None,
    ) -> float:
        return 1.0 if result.ok else -1.0


def resolve_reward(
    provider: RewardProvider | None,
    result: StepResult,
    *,
    actor_id: str,
    context: dict[str, Any] | None = None,
) -> tuple[float, str]:
    """Return ``(reward, reward_status)`` using neutral defaults when unconfigured."""
    if provider is None:
        return NeutralRewardProvider().reward(result, actor_id=actor_id, context=context), (
            REWARD_STATUS_UNCONFIGURED
        )
    return (
        float(provider.reward(result, actor_id=actor_id, context=context)),
        REWARD_STATUS_CONFIGURED,
    )
