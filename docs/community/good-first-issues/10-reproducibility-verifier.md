# GFI-10: Reproducibility verifier

## Problem

Reproduction bundles must verify digests and expected outputs **without** a
source checkout. Contributors can own a focused verifier script used by
`reproduce.yml`’s download-only job.

## Intended claim

Given a published bundle layout, verification fails closed on digest mismatch.
Does **not** claim bit-identical results across all hardware without a platform
record.

## Deliverable

- `verify.sh` / Python verifier consuming `MANIFEST.json` + expected digests
- Pytest with a tiny synthetic bundle (pass + tamper fail)
- Docs pointer under reproducibility page

## Files

- `reproducibility/verify.sh` or `scripts/verify_repro_bundle.py`
- `reproducibility/MANIFEST.json` schema notes / fixture under `tests/`
- `tests/reproducibility/test_verify_bundle.py`
- `docs/reproducibility.md`

## Tests

- Untampered fixture → pass
- Bit-flipped artifact → fail
- Missing platform record → fail or explicit indeterminate per design (document)

## Non-goals

- Building the full release signing pipeline
- Replacing pack `eac pack verify`
- Silent repair of mismatched digests
- Auth / snapshot redesign

## Reviewer

Repro / release area owner (`CODEOWNERS` for reproducibility + release workflows).

## Status

`proposed` — good first issue
