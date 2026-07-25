"""Delta-debugging style counterexample minimization with reduction steps."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import Diagnostic

T = TypeVar("T")


@dataclass(slots=True)
class ReductionStep:
    """One recorded reduction during minimization."""

    iteration: int
    kind: str
    before_len: int
    after_len: int
    kept: list[Any]


@dataclass(slots=True)
class MinimizationResult:
    """Result of shrinking a failing sequence while preserving the failure."""

    original: list[Any]
    minimized: list[Any]
    iterations: int
    preserved_failure: bool
    diagnostics: list[Diagnostic] = field(default_factory=list)
    reduction_steps: list[ReductionStep] = field(default_factory=list)

    @property
    def shrunk(self) -> bool:
        return len(self.minimized) < len(self.original)


def minimize_counterexample(
    sequence: Sequence[T],
    fails: Callable[[Sequence[T]], bool],
    *,
    probe_id: str = "ce",
    max_iterations: int = 10_000,
) -> MinimizationResult:
    """
    Shrink *sequence* with ddmin while *fails* remains true on the subset.

    Classic delta-debugging: partition into 2^n granules, keep failing subsets,
    increase granularity when no progress. Each accepted reduction is recorded
    in ``reduction_steps``.
    """
    original = list(sequence)
    if not original:
        return MinimizationResult(
            original=[],
            minimized=[],
            iterations=0,
            preserved_failure=False,
        )
    if not fails(original):
        return MinimizationResult(
            original=original,
            minimized=list(original),
            iterations=0,
            preserved_failure=False,
        )

    current = list(original)
    n = 2
    iterations = 0
    steps: list[ReductionStep] = []

    def _record(kind: str, before: list[T], after: list[T]) -> None:
        steps.append(
            ReductionStep(
                iteration=iterations,
                kind=kind,
                before_len=len(before),
                after_len=len(after),
                kept=list(after),
            )
        )

    while len(current) > 1 and iterations < max_iterations:
        iterations += 1
        subsets = _partition(current, n)
        reduced = False
        for subset in subsets:
            iterations += 1
            if iterations > max_iterations:
                break
            if subset and fails(subset):
                before = list(current)
                current = list(subset)
                _record("subset", before, current)
                n = 2
                reduced = True
                break
        if reduced:
            continue
        for subset in subsets:
            iterations += 1
            if iterations > max_iterations:
                break
            complement = _complement(current, subset)
            if complement and fails(complement):
                before = list(current)
                current = complement
                _record("complement", before, current)
                n = max(n - 1, 2)
                reduced = True
                break
        if reduced:
            continue
        if n >= len(current):
            break
        n = min(len(current), n * 2)

    changed = True
    while changed and len(current) > 1 and iterations < max_iterations:
        changed = False
        for i in range(len(current)):
            iterations += 1
            candidate = current[:i] + current[i + 1 :]
            if candidate and fails(candidate):
                before = list(current)
                current = candidate
                _record("drop_one", before, current)
                changed = True
                break

    diagnostics: list[Diagnostic] = []
    if len(current) < len(original):
        diagnostics.append(
            make_diagnostic(
                "EAC7003",
                reason=f"shrunk {len(original)} → {len(current)} steps for probe {probe_id}",
                subject=probe_id,
                details={
                    "original_len": len(original),
                    "minimized_len": len(current),
                    "reduction_step_count": len(steps),
                },
            )
        )

    return MinimizationResult(
        original=original,
        minimized=current,
        iterations=iterations,
        preserved_failure=fails(current),
        diagnostics=diagnostics,
        reduction_steps=steps,
    )


def _partition(seq: list[T], n: int) -> list[list[T]]:
    if n <= 1:
        return [list(seq)]
    n = min(n, len(seq))
    size = len(seq) / n
    parts: list[list[T]] = []
    for i in range(n):
        start = int(i * size)
        end = int((i + 1) * size)
        parts.append(seq[start:end])
    return [p for p in parts if p]


def _complement(seq: list[T], subset: list[T]) -> list[T]:
    if not subset:
        return list(seq)
    sub_len = len(subset)
    for i in range(0, len(seq) - sub_len + 1):
        if seq[i : i + sub_len] == subset:
            return seq[:i] + seq[i + sub_len :]
    return [x for x in seq if x not in subset]
