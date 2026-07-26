# GFI-02: Release-manifest validator

## Problem

Release manifests (`release-manifest.json` / schema under `schemas/`) must be
validated before attach-to-release. A small validator helps contributors catch
schema drift without running the full release workflow.

## Intended claim

Given a manifest path, validation reports schema and required-field errors with
non-zero exit. Does **not** claim cryptographic verification of artifacts (that
is checksum / attestation territory).

## Deliverable

- CLI or script: validate manifest against
  `schemas/release-manifest-1.json` (or current schema path once Milestone A lands)
- Pytest covering valid fixture + missing digest / version mismatch cases
- Docs blurb under contributing or release-process

## Files

- `scripts/validate_release_manifest.py` or `src/envassure/packaging/release_manifest.py`
- `schemas/release-manifest-*.json` (consume; do not redesign without release owners)
- `tests/packaging/test_release_manifest_validate.py`
- `docs/contributing/release-process.md` (link only)

## Tests

- Valid minimal fixture → exit 0
- Missing required field → exit non-zero + stable message
- Digest format rejection (`sha256:` expected)

## Non-goals

- Publishing to PyPI / GHCR
- Replacing Cosign / SBOM attestation flows
- Changing tag-signing policy
- Security-boundary redesign

## Reviewer

Packaging / release area owner (`CODEOWNERS` for `schemas/`, packaging, release workflows).

## Status

`proposed` — good first issue
