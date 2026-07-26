# GFI-07: Connector timeout fixture

## Problem

Differential / reference-connector tests need an offline fixture that simulates
timeouts and partial failures so `failure_agreement` is exercisable without a
live network. Related placeholder: [`ENV-2026-0001`](https://github.com/fraware/environment-assurance-compiler/blob/main/registry/environment-defects/ENV-2026-0001.yaml).

## Intended claim

Offline probes can observe timeout / partial-failure outcomes as first-class
dimensions. Does **not** claim production parity with a real refund service.

## Deliverable

- Fixture under `tests/fixtures/differential/` or `examples/*/sim/`
- Connector fake / stub returning timeout and partial failure
- Test asserting dimension reporting (not collapsed into a single score)
- Optional update to `ENV-2026-0001` digests when fixture hashes stabilize

## Files

- `tests/fixtures/differential/timeout_partial_failure.*` (new)
- `src/envassure/differential/` or connector test doubles
- `tests/differential/test_connector_timeout_fixture.py`
- `registry/environment-defects/ENV-2026-0001.yaml` (link / digest update only)

## Tests

- Probe run completes offline
- Timeout path marked failed / indeterminate per design (fail closed on missing evidence)
- Metrics expose failure dimension separately

## Non-goals

- Full HTTP+PostgreSQL refund service (Milestone C3 owners)
- Live network flakiness tests as the only coverage
- Authorization policy redesign
- Snapshot / security-boundary work

## Reviewer

Differential / connectors area owner (`CODEOWNERS` for differential + connector paths).

## Status

`proposed` — good first issue
