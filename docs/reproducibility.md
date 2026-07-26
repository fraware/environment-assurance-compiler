# Reproducibility

Status: **bundle layout and verify-without-checkout are Milestone D**. This page
states the intended contract so docs IA is complete for the public beta plan.

## Goals

- Publish a reproducibility bundle with `MANIFEST.json`, expected digests, and
  hardware / platform records.
- Provide `reproduce.sh` / `verify.sh` that a second CI job can run after
  downloading artifacts **without** a source checkout.
- Keep offline fixtures as the default for PR gates; live connectors remain
  opt-in.

## What exists today

- Example contract scripts under `examples/*/run.sh` and `verify.sh` (E1 refund
  is the first complete public example).
- Offline benchmarks and differential fixtures (see
  [Benchmarks](research/benchmarks.md)).
- Supply-chain verification notes:
  [Supply chain](security/supply-chain.md).

## Planned layout (indicative)

```text
reproducibility/
  MANIFEST.json
  expected/
  scripts/reproduce.sh
  scripts/verify.sh
  platform-record.json
```

Exact paths may land under `reproducibility/` in-tree or as CI-generated
release assets. Prefer verifying published digests over rebuilding from a dirty
working tree.

## Related

- [Benchmark packs](packs/benchmark-packs.md)
- [Package and publish](guides/package-and-publish.md)
- [Release process](contributing/release-process.md)
