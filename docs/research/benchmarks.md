# Benchmarks

Offline fixture-oracle harness for regression and research ablations. **No
network** and no live connectors are required.

## Run

```bash
eac benchmark benchmarks/fixtures/counter_oracle.json --json
eac benchmark benchmarks/fixtures/auth_oracle.json --json
eac benchmark benchmarks/fixtures/inventory_oracle.json --json
```

Fixture layout lives under
[`benchmarks/fixtures/`](https://github.com/fraware/environment-assurance-compiler/tree/main/benchmarks/fixtures).
See [`benchmarks/README.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/benchmarks/README.md).

## What results mean

Benchmark exit success means the oracle checks passed for the declared
expectations. It is **not** a composite fidelity leaderboard and does not
substitute for differential evidence against a real system under test.

## Related

- [Methodology](methodology.md)
- [Differentially validate](../guides/differentially-validate.md)
