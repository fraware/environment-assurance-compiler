# Fidelity claims guide

Fidelity in EnvAssure is a **multi-dimensional profile**, not a single score.
This guide explains how to make and review claims without overstating evidence.

## Rules of thumb

1. **Build success ≠ fidelity.** `eac build-ir`, `eac lint`, and `eac package`
   mean artifacts are well-formed enough to inspect.
2. **Every claim cites artifacts.** Declared levels (`EF-0`…`EF-5`, assurance
   profiles) must point at diagnostics, differential reports, decisions, coverage,
   or pack contents — not marketing language.
3. **Indeterminate stays visible.** Missing dimensions, underpowered samples, or
   unsupported semantics must not be collapsed into “match” or “pass.”
4. **Imports are facts.** OpenAPI / DDL / SOP / traces feed reconciliation; they
   are not a finished world.

## Claim → evidence map

| Claim shape | Minimum evidence |
| ----------- | ---------------- |
| Structural soundness | `eac lint` / `eac analyze` clean for the declared profile |
| Deterministic replay | `eac test` / `eac replay` digests |
| Differential parity (scoped) | `eac differential` with fixtures; dimension-separated results |
| Expert interpretations | Closed ambiguities via `eac decide` with rationale |
| Pack integrity | `eac verify-pack` (checksums + secret scan) — not fidelity |

## Writing a claim in reports

Prefer language like:

> Under fixture set *F* and probe plan *P*, dimensions *D* showed match; dimension
> *latency* was indeterminate (insufficient samples). Open ambiguity *AMB-…*
> remains unresolved; release IR excludes unresolved facts.

Avoid:

> This pack proves production equivalence.

## Reviewer checklist

- [ ] Claim names the environment id, IR version, and profile
- [ ] Evidence paths are reproducible offline where possible
- [ ] Negative / indeterminate results are published, not dropped
- [ ] Optional extras / network connectors are not implied as proof of parity

## Related

- [Validation and fidelity](../concepts/validation-and-fidelity.md)
- [Limitations](../research/limitations.md)
- [Release readiness 0.2](../research/release-readiness-0.2.md)
- [Differentially validate](differentially-validate.md)
