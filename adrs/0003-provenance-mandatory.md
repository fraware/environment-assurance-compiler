# ADR-0003: Provenance Is Mandatory

- Status: Accepted
- Date: 2026-07-25

## Context

Environments built from heterogeneous sources (APIs, schemas, traces, SOPs,
expert decisions, model proposals) lose trust if derived artifacts cannot be
traced to inputs and decisions.

## Decision

Every IR element, fact, ambiguity, decision, and pack artifact carries provenance
links. Model proposals are never authoritative source facts; they require an
explicit `model_proposal` origin and human acceptance path.

## Consequences

- `eac explain` can walk IR back to sources and decisions.
- Content-addressed digests (canonical JSON) pin artifacts in lock files.
- Missing provenance is a diagnostic defect for release-grade packs.
- Silent invention of timeout/retry/idempotency semantics is forbidden.
