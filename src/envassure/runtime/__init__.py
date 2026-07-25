"""EnvAssure reference runtime: protocol, event-sourced engine, codegen, adapters."""

from __future__ import annotations

from envassure.runtime.codegen import generate_runtime_module, write_runtime_module
from envassure.runtime.engine import (
    EventSourcedEnvironment,
    RuntimeError_,
    StrictMutationError,
)
from envassure.runtime.events import Event, SideEffectIntent, StepResult
from envassure.runtime.protocol import AssuredEnvironment
from envassure.runtime.snapshot import Snapshot

__all__ = [
    "AssuredEnvironment",
    "Event",
    "EventSourcedEnvironment",
    "RuntimeError_",
    "SideEffectIntent",
    "Snapshot",
    "StepResult",
    "StrictMutationError",
    "generate_runtime_module",
    "write_runtime_module",
]
