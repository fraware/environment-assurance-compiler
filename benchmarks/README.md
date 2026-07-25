# Offline benchmark fixtures

Local fixture oracles for the hidden-reference / generator harness.
No network and no live connectors are required.

```bash
eac benchmark benchmarks/fixtures/counter_oracle.json --json
eac benchmark benchmarks/fixtures/auth_oracle.json --json
eac benchmark benchmarks/fixtures/inventory_oracle.json --json
eac benchmark --suite --json
# Full offline concealed suite (≥100 curated + ≥100 generated probes per workflow):
eac benchmark --concealed --json
# CI keeps a capped run for PR latency:
eac benchmark --concealed --max-probes 20 --json
```

Concealed workflow manifests (`transactional_enterprise.json`,
`authorization_heavy.json`, `stochastic_operational.json`) declare a
`generator` id and pinned `hidden_oracle_digest`. Episodes are materialized by
`envassure.benchmark.workflows.build_workflow_oracle` (≥100 curated + ≥100
generated probes each when uncapped).

A schedule workflow (`.github/workflows/nightly-empirical.yml`) runs the
uncapped concealed suite without network secrets; PR CI stays capped.

See [docs/research/benchmarks.md](../docs/research/benchmarks.md) for
dimension-separated metrics, published negative results, and the independent
reproduction checklist.
