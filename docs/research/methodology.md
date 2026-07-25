# Research methodology

EnvAssure treats environment assurance as an empirical, artifact-backed process:

1. **Declare evidence** — sources with authority and digests.
2. **Compile explicitly** — IR with provenance; no silent invention of missing
   semantics.
3. **Analyze statically** — reference integrity, reachability, authority,
   information flow, termination / retry consistency.
4. **Exercise dynamically** — reset / step / replay / property tests.
5. **Compare differentially** — typed dimensions against fixtures or simulators.
6. **Close decisions** — ambiguities resolved by named experts with rationale.
7. **Report dimensions** — assurance-case JSON/HTML without collapsing to a
   single fidelity score ([ADR-0005](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0005-fidelity-profile.md)).

## Offline-first evaluation

CI and published benchmarks should run without network. Use:

- `tests/fixtures/differential/` and `examples/*/sim/` for connectors
- `eac benchmark` with fixtures under `benchmarks/fixtures/`
- mutation categories in `envassure.analysis.mutation` for detector checks

## Ablations

When reporting research results, ablate by evidence class (drop traces, drop
expert decisions, weaken observation constraints) and report which diagnostic
families fire. Do not claim production fidelity from synthetic in-memory
connectors alone.

See also [Benchmarks](benchmarks.md) and [Limitations](limitations.md).
