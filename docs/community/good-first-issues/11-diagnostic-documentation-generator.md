# GFI-11: Diagnostic documentation generator

## Problem

Diagnostics live in `envassure.diagnostics.catalog` and must stay listed in
[`docs/reference/diagnostics.md`](../../reference/diagnostics.md). A generator
reduces drift when new `EAC####` codes land.

## Intended claim

Docs diagnostics table can be regenerated from the catalog and checked in CI for
drift. Does **not** claim diagnostic UX redesign.

## Deliverable

- Script: catalog → markdown table / sections
- CI check: generated content matches committed docs (or `--check` mode)
- Note in contributing checklist

## Files

- `scripts/generate_diagnostics_docs.py` (new)
- `src/envassure/diagnostics/catalog.py` (read-only)
- `docs/reference/diagnostics.md` (generated region or full file policy — document choice)
- `tests/diagnostics/test_docs_generator.py`
- `CONTRIBUTING.md` or `docs/contributing/development.md` (one-line)

## Tests

- Generator is deterministic
- `--check` fails when a catalog entry is missing from docs
- Round-trip on current catalog passes

## Non-goals

- Renaming diagnostic codes
- Changing severity policy
- New CLI surface beyond the generator script
- Auth / snapshot / security-boundary work

## Reviewer

Diagnostics area owner (`CODEOWNERS` for `src/envassure/diagnostics/`, `docs/reference/diagnostics.md`).

## Status

`proposed` — good first issue
