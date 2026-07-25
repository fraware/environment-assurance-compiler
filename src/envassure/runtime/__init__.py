"""EnvAssure reference runtime: protocol, event-sourced engine, codegen, adapters."""

from __future__ import annotations

from envassure.runtime.codegen import generate_runtime_module, write_runtime_module
from envassure.runtime.engine import (
    EventSourcedEnvironment,
    RuntimeError_,
    StrictMutationError,
)
from envassure.runtime.events import Event, SideEffectIntent, StepResult, TransactionReceipt
from envassure.runtime.external import EffectReceipt, ExternalEffectExecutor
from envassure.runtime.observations import (
    CompiledObservation,
    ObservationError,
    compile_observation,
    project_state,
)
from envassure.runtime.outcomes import StepOutcome, TransitionStatus
from envassure.runtime.protocol import AssuredEnvironment
from envassure.runtime.snapshot import Snapshot

__all__ = [
    "AssuredEnvironment",
    "CompiledObservation",
    "EffectReceipt",
    "Event",
    "EventSourcedEnvironment",
    "ExternalEffectExecutor",
    "ObservationError",
    "RuntimeError_",
    "SideEffectIntent",
    "Snapshot",
    "StepOutcome",
    "StepResult",
    "StrictMutationError",
    "TransactionReceipt",
    "TransitionStatus",
    "compile_observation",
    "generate_runtime_module",
    "project_state",
    "write_runtime_module",
]
