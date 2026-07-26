# Benchmark packs

Status: **contract documented; signed pack assets are Milestone D**.

EnvAssure distinguishes:

| Artifact | Role |
| -------- | ---- |
| Environment Pack (`.eap`) | Compiled world + provenance members (`eac package` / `eac verify-pack`) |
| Benchmark pack | Research / regression suite with conflicts, ambiguities, baselines, mutations |

Do not conflate `eac package` / `verify-pack` with the planned
`eac pack lint|verify|reproduce|inspect` group for benchmark packs.

## Planned release packs

1. `envassure-transactional-refund`
2. `envassure-delegated-authorization`
3. `envassure-stochastic-operations`

Each must include source conflict, open ambiguity, hidden reference behavior,
unsupported-use declaration, baseline, mutation suite, and differential plan.
Mapping from existing concealed suites under `benchmarks/` /
`envassure.benchmark` is expected where possible.

## Today

- Offline fixture harness: [Research benchmarks](../research/benchmarks.md).
- Contribution guide for pack authors:
  [Benchmark packs (contributing)](../contributing/benchmark-packs.md).

## Related

- [Reproducibility](../reproducibility.md)
- [Governance](../governance/index.md)
