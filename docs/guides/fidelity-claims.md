# Fidelity claims guide

Fidelity in EnvAssure is a **multi-dimensional profile**, not a single score
([ADR-0005](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0005-fidelity-profile.md)).
Scoped claims live in the **fidelity ledger** (`FidelityClaim` / `FidelityLedger`),
which is the source of truth for assurance-case sections **§20.3** (profile) and
**§20.4** (claims and evidence). Packs embed the ledger at `fidelity/ledger.json`.

## Ledger schema

Each `FidelityClaim` records:

| Field | Role |
| ----- | ---- |
| `claim` | Scoped statement (what is asserted) |
| `scope` | Required: `environment_id` plus `element_ids` and/or `dimension` |
| `evidence` | Artifact refs (digests, paths, probe ids) |
| `coverage` | What the evidence covers (fixture set, probe plan, etc.) |
| `reviewer` | Optional expert identity when reviewed |
| `known_gaps` | Explicit gaps / indeterminate dimensions |
| `status` | Assessment ladder (see below) |

Allowed `status` values (ascending evidence strength):

1. `unassessed`
2. `structurally_valid`
3. `trace_supported`
4. `expert_reviewed`
5. `empirically_compared`

**Hard rules**

- No aggregate / composite / average score field exists on the ledger or report.
- Averaging APIs (`average_fidelity_score`, `mean_fidelity`, …) raise `ValueError`.
- `scope` is required; claims without environment + element set or dimension are rejected.
- When `status` is below `expert_reviewed`, `known_gaps` must remain non-empty and visible.

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

| Claim shape | Minimum evidence | Typical ledger status |
| ----------- | ---------------- | --------------------- |
| Structural soundness | `eac lint` / `eac analyze` clean for the declared profile | `structurally_valid` |
| Deterministic replay | `eac test` / `eac replay` digests | `trace_supported` |
| Differential parity (scoped) | `eac differential` with fixtures; dimension-separated results | `empirically_compared` |
| Expert interpretations | Closed ambiguities via `eac decide` with rationale | `expert_reviewed` |
| Pack integrity | `eac verify-pack` (checksums + secret scan) — not fidelity | (not a fidelity claim) |

## Writing a claim in reports

Prefer language like:

> Under fixture set *F* and probe plan *P*, dimensions *D* showed match; dimension
> *latency* was indeterminate (insufficient samples). Open ambiguity *AMB-…*
> remains unresolved; release IR excludes unresolved facts.

Avoid:

> This pack proves production equivalence.

`eac report` and `eac package` accept `--fidelity ledger.json`. When omitted,
they seed a ledger from declared IR fields (`structurally_valid`); replace it
with reviewed claims before release-grade language.

## Reviewer checklist

- [ ] Claim names the environment id, IR version, and profile / dimension
- [ ] Evidence paths are reproducible offline where possible
- [ ] Negative / indeterminate results are published in `known_gaps`, not dropped
- [ ] Optional extras / network connectors are not implied as proof of parity
- [ ] No composite score or averaged dimension summary appears in the claim text

## Related

- [Validation and fidelity](../concepts/validation-and-fidelity.md)
- [Limitations](../research/limitations.md)
- [Release readiness 0.2](../research/release-readiness-0.2.md)
- [Differentially validate](differentially-validate.md)
