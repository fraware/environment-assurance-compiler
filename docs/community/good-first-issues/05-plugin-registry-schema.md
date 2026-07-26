# GFI-05: Plugin-registry schema (CI + contribution path)

## Problem

[`schemas/plugin-registry-v1.schema.json`](https://github.com/fraware/environment-assurance-compiler/blob/main/schemas/plugin-registry-v1.schema.json)
and [`registry/plugins-v1.json`](https://github.com/fraware/environment-assurance-compiler/blob/main/registry/plugins-v1.json) exist as
curated metadata. Contributors still need CI validation and a clear PR checklist
so the registry never becomes an auto-installer.

## Intended claim

Registry JSON always conforms to the schema in CI; contribution docs state
**never auto-install**. Does **not** claim security review of third-party code.

## Deliverable

- CI job or pytest that validates `registry/plugins-v1.json`
- Contribution section (plugins guide or `registry/README.md` expansion)
- Optional: dry-run entry in a test fixture (not merged into the live registry)
  exercising every `review_status` enum value against the schema

## Files

- `schemas/plugin-registry-v1.schema.json`
- `registry/plugins-v1.json`
- `registry/README.md`
- `tests/registry/test_plugins_v1_schema.py` (new)
- `docs/guides/author-plugins.md` or `docs/community/index.md` (checklist link)

## Tests

- Live registry validates
- Mutated registry (drop `release_digest`) fails
- Fixture entry with each status enum validates

## Non-goals

- Auto-install or `pip install` from registry entries
- Trusting plugins without allowlist / digest lock
- Implementing new plugin kinds in core
- Security-boundary redesign

## Reviewer

Plugins / supply-chain area owner (`CODEOWNERS` for `registry/`, `src/envassure/plugins/`).

## Status

`proposed` — good first issue
