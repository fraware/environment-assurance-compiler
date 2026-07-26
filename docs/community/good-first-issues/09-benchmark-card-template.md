# GFI-09: Benchmark-card template

## Problem

Published packs and concealed suites need a consistent “benchmark card”
(construct, metrics, version, limitations, custody notes) for humans and grant
reproductions.

## Intended claim

A template exists and at least one pack/fixture fills it. Does **not** claim the
card is a leaderboard or composite fidelity score.

## Deliverable

- Markdown or YAML template under `docs/` or `benchmarks/`
- Alignment with [benchmark charter](../../governance/benchmark-charter.md)
  versioning rules (major/minor/patch)
- One filled example (e.g. transactional refund or counter oracle)
- Index link from `docs/research/benchmarks.md`

## Files

- `benchmarks/cards/TEMPLATE.md` (or `.yaml`) (new)
- `benchmarks/cards/<workflow>.md` (one example)
- `docs/research/benchmarks.md`
- `docs/governance/benchmark-charter.md` (cross-link only)

## Tests

- Template headings present (lint script or pytest reading required sections)
- Example card references a real fixture path that exists
- Version field present and non-empty

## Non-goals

- Changing hidden oracles or primary metrics (major bump; not good-first)
- OCI pack distribution
- Collapsing dimensions into one score
- Security-boundary work

## Reviewer

Benchmarks area owner (`CODEOWNERS` for `benchmarks/`, `src/envassure/benchmark/`).

## Status

`proposed` — good first issue
