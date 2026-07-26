"""EnvAssure reference runtime: protocol, event-sourced engine, codegen, adapters."""

from __future__ import annotations

from envassure.runtime.codegen import generate_runtime_module, write_runtime_module
from envassure.runtime.engine import (
    EventSourcedEnvironment,
    RuntimeError_,
    StrictMutationError,
)
from envassure.runtime.events import (
    Event,
    EventLogValidationError,
    SideEffectIntent,
    StepResult,
    TerminalRecord,
    TransactionReceipt,
    TransitionDecision,
    reconstruct_state,
    validate_event_log,
)
from envassure.runtime.external import (
    EffectReceipt,
    ExternalEffectExecutor,
    SideEffectResult,
)
from envassure.runtime.intent_ids import (
    canonical_effect_payload_digest,
    make_intent_id,
    make_transaction_id,
)
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
    "EventLogValidationError",
    "EventSourcedEnvironment",
    "ExternalEffectExecutor",
    "ObservationError",
    "RuntimeError_",
    "SideEffectIntent",
    "SideEffectResult",
    "Snapshot",
    "StepOutcome",
    "StepResult",
    "StrictMutationError",
    "TerminalRecord",
    "TransactionReceipt",
    "TransitionDecision",
    "TransitionStatus",
    "canonical_effect_payload_digest",
    "compile_observation",
    "generate_runtime_module",
    "make_intent_id",
    "make_transaction_id",
    "project_state",
    "reconstruct_state",
    "validate_event_log",
    "write_runtime_module",
]
