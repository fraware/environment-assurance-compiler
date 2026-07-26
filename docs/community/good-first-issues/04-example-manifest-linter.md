# GFI-04: Example-manifest linter

## Problem

Public examples must follow the example contract (`README`, `run.sh`,
`verify.sh`, `example-manifest.json`, `input/`, `expected/`, …). A linter
catches incomplete scaffolds before release CI.

## Intended claim

`example-manifest.json` files and required sibling paths are structurally
valid. Does **not** claim that `run.sh` semantics match production fidelity.

## Deliverable

- Linter script or `eac` subcommand helper that checks declared paths exist
- JSON schema or dataclass for `example-manifest.json` if missing
- CI step over `examples/**/example-manifest.json`
- One fixed fixture example (E1 refund) used as golden

## Files

- `scripts/lint_example_manifests.py` (or under `src/envassure/packaging/`)
- `schemas/example-manifest-1.json` (new if absent)
- `examples/*/example-manifest.json`
- `tests/examples/test_example_manifest_lint.py`

## Tests

- Golden refund (or stub) manifest passes
- Missing `verify.sh` fails
- Unknown required key / bad version fails

## Non-goals

- Implementing all of E2–E5 content
- Networked example runs
- Changing IR semantics
- Auth / snapshot redesign

## Reviewer

Docs / examples area owner (`CODEOWNERS` for `examples/**`).

## Status

`proposed` — good first issue
