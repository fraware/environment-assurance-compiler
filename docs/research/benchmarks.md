# Benchmarks

Offline fixture-oracle harness for regression and research ablations. **No
network** and no live connectors are required.

## Run

Small regression fixtures:

```bash
eac benchmark benchmarks/fixtures/counter_oracle.json --json
eac benchmark benchmarks/fixtures/auth_oracle.json --json
eac benchmark benchmarks/fixtures/inventory_oracle.json --json
eac benchmark --suite --json
```

Concealed hidden-reference suite (EAC-R15) — three workflows with ≥100 curated
and ≥100 generated probes each (uncapped local / nightly run):

```bash
eac benchmark --concealed --json
eac benchmark benchmarks/fixtures/transactional_enterprise.json --json
eac benchmark benchmarks/fixtures/authorization_heavy.json --json
eac benchmark benchmarks/fixtures/stochastic_operational.json --json
```

PR CI caps the same suite at `--max-probes 20` for latency; the schedule
workflow `.github/workflows/nightly-empirical.yml` runs uncapped (offline, no
secrets).

Fixture layout lives under
[`benchmarks/fixtures/`](https://github.com/fraware/environment-assurance-compiler/tree/main/benchmarks/fixtures).
See [`benchmarks/README.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/benchmarks/README.md).

## Concealed workflows

| Workflow | Focus |
| --- | --- |
| `transactional_enterprise` | Ledger / refund / idempotency / retry |
| `authorization_heavy` | Multi-role deny paths and observation separation |
| `stochastic_operational` | Categorical stockout branches; underpowered samples |

Metrics are **dimension-separated** (`transition_agreement`, `auth_agreement`,
`failure_agreement`, `observation_agreement`, `leakage`, `solvability`,
`diff_match`). Do not collapse them into a single fidelity score.

Oracle digests are pinned by `envassure.benchmark.workflows` (seed `0`). Manifest
files under `benchmarks/fixtures/<workflow>.json` carry `generator` +
`hidden_oracle_digest` without shipping the full answer key as the only path.

## Negative results (published)

Intentional mismatches are retained in the concealed generators:

- Candidate fail-open authorization (approve without role)
- Observation leakage of evaluator-only fields (`approver_id`, `true_fill_rate`,
  `internal_risk_score`)
- Underpowered stochastic probes treated as success by a buggy candidate
  (must remain non-pass / visible leakage — never scored as clean match)

Reports expose `metadata.negative_probe_count` and per-episode
`metadata.negative`. Suppressing negatives is a methodology failure.

## Independent reproduction checklist

1. Clean install from the tested tag/commit (`pip install -e ".[dev]"` or wheel).
2. Confirm `python -c "import envassure; print(envassure.__version__)"`.
3. Run `eac benchmark --concealed --json` (offline; no network).
4. For each workflow, verify `episode_count >= 200` at default curated/generated
   counts (100+100) and that `oracle_digest` matches the manifest
   `hidden_oracle_digest` for seed `0`.
5. Confirm dimension metrics are present individually; do not average.
6. Confirm `negative_probe_count > 0` for each workflow.
7. Optionally re-materialize digests:

   ```python
   from envassure.benchmark.workflows import oracle_digest_for, WORKFLOW_IDS
   for wid in WORKFLOW_IDS:
       print(wid, oracle_digest_for(wid, seed=0))
   ```

8. Record OS, Python version, and package digest alongside results.

## What results mean

Benchmark exit success means the oracle checks passed for the declared
expectations. It is **not** a composite fidelity leaderboard and does not
substitute for differential evidence against a real system under test.

## Related

- [Methodology](methodology.md)
- [Limitations](limitations.md)
- [Differentially validate](../guides/differentially-validate.md)
