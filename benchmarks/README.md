# Offline semantic regression fixtures

These fixtures exercise EnvAssure's benchmark/differential machinery locally.
They are useful for deterministic regression, negative-control preservation,
and metric plumbing. **They are not a concealed environment-construction
benchmark and are not evidence of fidelity to an independently implemented
reference system.**

No network and no live connectors are required.

```bash
eac benchmark benchmarks/fixtures/counter_oracle.json --json
eac benchmark benchmarks/fixtures/auth_oracle.json --json
eac benchmark benchmarks/fixtures/inventory_oracle.json --json
eac benchmark --suite --json
# Historical CLI name retained for compatibility. This executes the larger
# generated semantic-regression suite; it is NOT qualification-grade concealment.
eac benchmark --concealed --json
# CI keeps a capped run for PR latency:
eac benchmark --concealed --max-probes 20 --json
```

The three generated workflow manifests (`transactional_enterprise.json`,
`authorization_heavy.json`, `stochastic_operational.json`) declare a generator
id and pinned oracle digest. Episodes are materialized by
`envassure.benchmark.workflows.build_workflow_oracle` (>=100 curated + >=100
generated probes each when uncapped).

Because the generator implementation is shipped in this repository and
constructs the oracle/candidate fixture data, the `--concealed` option name is
historical API terminology only. It MUST NOT be cited as evidence that source
semantics were reconstructed without access to the reference implementation or
that held-out behavior was concealed from the system under evaluation.

A schedule workflow (`.github/workflows/nightly-empirical.yml`) runs the
uncapped semantic-regression suite without network secrets; PR CI stays capped.

See [docs/research/benchmarks.md](../docs/research/benchmarks.md) for the claim
boundary and the qualification-grade hidden-reference protocol that remains to
be executed against independent reference systems.
