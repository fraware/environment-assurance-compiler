# GFI-12: Windows pack-path regression

## Problem

Packaging and pack verify can break on Windows path separators, long paths, or
zip member names. A focused regression test prevents Unix-only assumptions.

## Intended claim

Pack create / verify (Environment Pack `.eap` and/or benchmark pack paths)
succeeds on Windows for a minimal fixture. Does **not** claim full feature
parity of every optional extra on Windows.

## Deliverable

- Pytest marked for Windows (and runnable on Unix with `pathlib` assertions)
- Fixture that embeds nested paths and spaces if relevant
- CI inclusion on `windows-latest` job if not already present
- Short troubleshooting note in package/publish or contributing docs

## Files

- `tests/packaging/test_windows_pack_paths.py` (new)
- `src/envassure/packaging/` (fix only if test reveals bug)
- `.github/workflows/ci.yml` (ensure Windows tox/pytest runs this test)
- `docs/guides/package-and-publish.md` or `docs/contributing/development.md`

## Tests

- Round-trip pack with nested relative paths using `pathlib` only (no
  hardcoded `/` assumptions in assertions)
- Verify fails closed on tampered member without path-escape surprises
- Skip or xfail clearly if an optional dependency is absent

## Non-goals

- Rewriting the entire packaging subsystem
- Supporting UNC edge cases beyond what release CI claims
- Authorization / snapshot integrity redesign
- Auto-install of plugins

## Reviewer

Packaging / Windows CI area owner (`CODEOWNERS` for `src/envassure/packaging/`, CI workflows).

## Status

`proposed` — good first issue
