"""Typed step / transition outcomes (EAC-R01)."""

from __future__ import annotations

from enum import StrEnum


class StepOutcome(StrEnum):
    """Closed decision model for AssuredEnvironment.step results.

    Episode markers ``terminal`` / ``truncated`` appear as outcomes when they
    *are* the decision (e.g. already-terminal rejection, horizon truncation
    without a successful commit). Successful commits that also end the episode
    use ``success`` with ``StepResult.terminal`` / ``truncated`` flags set.
    """

    SUCCESS = "success"
    DENIED = "denied"
    INVALID_INPUT = "invalid_input"
    PRECONDITION_FAILED = "precondition_failed"
    UNSUPPORTED_SEMANTICS = "unsupported_semantics"
    EXTERNAL_FAILURE = "external_failure"
    INDETERMINATE = "indeterminate"
    TERMINAL = "terminal"
    TRUNCATED = "truncated"


# Alias retained for plan wording / external docs.
TransitionStatus = StepOutcome

# Outcomes that mutate authoritative state only when events commit successfully.
AUTHORITATIVE_COMMIT_OUTCOMES: frozenset[StepOutcome] = frozenset(
    {StepOutcome.SUCCESS, StepOutcome.TRUNCATED}
)


def outcome_is_ok(outcome: StepOutcome) -> bool:
    """Return True when the step committed (or truncated after a valid commit)."""
    return outcome in AUTHORITATIVE_COMMIT_OUTCOMES
