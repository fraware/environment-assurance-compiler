# ADR-0002: Event-Sourced Reference Runtime

- Status: Accepted
- Date: 2026-07-25

## Context

Assurance requires replay, snapshot/restore, fork, and differential comparison.
Mutable in-place worlds make provenance and counterexample minimization harder.

## Decision

The reference runtime is event-sourced: validated actions produce events and
side-effect intents that are applied atomically. Snapshots capture authoritative
state, actors, scheduled events, clock, RNG, audit head, digests, and task state.
Strict mode forbids out-of-band mutation.

## Consequences

- Replay and differential probes become first-class (`eac run|snapshot|replay|test`).
- Live external effects are opt-in; default records intents only.
- Packs declare determinism class (fully deterministic, seeded + recorded,
  statistical, or externally nondeterministic).
