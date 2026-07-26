# Benchmark packs (contributing)

How to author research / regression **benchmark packs** (distinct from
Environment Packs `.eap`).

## Distinction

| Command family | Artifact |
| -------------- | -------- |
| `eac package` / `eac verify-pack` | Environment Pack (`.eap`) |
| Planned `eac pack lint|verify|reproduce|inspect` | Benchmark pack |

See [Benchmark packs](../packs/benchmark-packs.md) for release intent.

## Required content (beta bar)

A public benchmark pack should include:

1. Source conflict material
2. At least one open ambiguity (or recorded decision with rationale)
3. Hidden reference behavior for concealed probes
4. Unsupported-use declaration
5. Baseline expectations
6. Mutation suite
7. Differential plan (offline preferred)

## Local work today

Until Milestone D lands schemas and CLI:

- Use fixtures under `benchmarks/fixtures/`.
- Run `eac benchmark …` per [Research benchmarks](../research/benchmarks.md).
- Do not publish unsigned packs as release assets.

## Related

- [Reproducibility](../reproducibility.md)
- [Governance](../governance/index.md)
- [Development](development.md)
