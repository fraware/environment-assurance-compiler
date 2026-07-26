# GFI-06: OPA evidence schema

## Problem

OPA obligation evaluation evidence must feed the assurance case with a stable
schema so reports and packs can cite digests without ad-hoc JSON.

## Intended claim

OPA evidence documents validate against a published schema and round-trip in
tests. Does **not** claim that Rego policies prove production authorization
correctness.

## Deliverable

- JSON Schema under `schemas/` (e.g. `opa-evidence-1.json`)
- Emitter or dataclass aligned with obligations evidence module
- Pytest for minimal pass / fail / indeterminate evidence fixtures
- Docs link from OPA integration page when present

## Files

- `schemas/opa-evidence-1.json` (new)
- `src/envassure/obligations/` (evidence emitter; extend, do not redesign IR)
- `tests/obligations/test_opa_evidence_schema.py`
- `docs/integrations/opa.md` (link)

## Tests

- Valid evidence fixture validates
- Missing digest / obligation id fails
- Assurance-case consumer accepts the fixture (smoke)

## Non-goals

- Rewriting authorization semantics in the core runtime
- Vendoring the OPA binary into the base wheel
- Snapshot integrity changes
- Good-first work on security-boundary redesign

## Reviewer

Obligations / integrations area owner (`CODEOWNERS` for `src/envassure/obligations/`).

## Status

`proposed` — good first issue
