# GFI-01: Docs-link checker

## Problem

MkDocs `--strict` catches some broken pages, but internal/external link drift
and version-alias links still slip through. Contributors need a focused checker
for docs IA.

## Intended claim

CI can fail closed on broken internal documentation links (and a controlled
external allowlist). This does **not** claim full website QA or content accuracy.

## Deliverable

- Script under `scripts/` (e.g. `check_docs_links.py`) or docs CI step
- Integration into docs workflow / `make` target if present
- Short note in `docs/contributing/development.md`

## Files

- `scripts/check_docs_links.py` (new)
- `.github/workflows/docs.yml` or `ci.yml` docs job (wire-up only)
- `docs/contributing/development.md`
- Optional: `tests/docs/test_docs_links.py`

## Tests

- Unit/integration test with a temporary markdown tree containing one broken
  relative link (must fail) and one valid link (must pass)
- Dry-run on repo `docs/` in CI

## Non-goals

- Rewriting the entire docs IA
- Scraping or load-testing the published GitHub Pages site
- Authorization / snapshot / security-boundary work
- Auto-fixing prose

## Reviewer

Docs / CI area owner (`CODEOWNERS` for `docs/**` and docs workflows).

## Status

`proposed` — good first issue
