# Independent reproduction grant call (engineering text)

This document is the **public call text** for independent reproduction work.
It defines eligibility, expected outputs, and methodological scoring.

**Out of band (not operated in this repository):** funding amounts, selection
committees, contracts, and payment. Do not open PRs that add payment ops,
invoices, or bank details.

Illustrative stipend ranges from the public-beta specification (compute
separate): three grants on the order of €3,000–€5,000 each. Actual offers, if
any, are handled outside this repo.

## Tracks

1. **Clean-room install and examples** — install from published index/image;
   run release-tested examples without an editable checkout.
2. **Hidden-reference benchmark reproduction** — reproduce concealed / pack
   suites from published digests and instructions.
3. **Adversarial challenge to an assurance claim** — attempt to falsify a
   published claim with evidence-backed defects.

## Eligibility (engineering)

Applicants should be able to demonstrate:

- Independent of the day-to-day release engineering for the challenged artifacts
  (disclose prior contributions and conflicts)
- Ability to run Linux and/or Windows verification as required by the track
- Commitment to publish negative results and contamination disclosures
- Agreement that EnvAssure must **not** auto-install registry plugins during the
  study

Security testing against production third-party systems requires explicit
authorization; prefer offline fixtures and published reference services.

## Required outputs

Every funded or volunteer reproduction under this call should produce:

| Output | Description |
| ------ | ----------- |
| Public report | Methods, environment, results, limitations |
| Exact environment | OS, Python, package/image digests, tool versions |
| Logs and digests | Command logs; SHA-256 of wheels, packs, bundles |
| Defects | Issues / [`ENV-*` records](https://github.com/fraware/environment-assurance-compiler/tree/main/registry/environment-defects) when fidelity gaps are found |
| Deviations | Where instructions failed or were ambiguous |
| Reusable test assets | Fixtures, probes, or scripts suitable for upstream CI |

## Methodological completeness scoring

Pay for (or credit) **methodological completeness**, not agreement with
maintainers. Suggested scorecard (0–2 each; sum / 20):

| Criterion | 0 | 1 | 2 |
| --------- | - | - | - |
| Environment record | Missing digests | Partial pins | Exact reproducible pins |
| Protocol fidelity | Ad-hoc steps | Mostly followed | Followed + noted ambiguities |
| Dimension separation | Collapsed score | Partial | Metrics kept separate |
| Negative results | Omitted | Mentioned | Documented with artifacts |
| Contamination disclosure | Silent risk | Partial | Explicit assessment |
| Defect quality | Vague | Reproducible | Registry-ready + residual limitation |
| Asset reuse | None | Scripts only | CI-ready fixtures |
| Independence | Conflicted / undisclosed | Disclosed | Clear independence |
| Claim hygiene | Overclaims | Cautious | Aligns with non-claims / limitations |
| Verification without checkout | Not attempted | Partial | Bundle / image path verified |

Minimum bar for “complete” under this call: **≥14/20** with no zero on
environment record, contamination disclosure, or claim hygiene.

## What this call does not buy

- Silent agreement with upstream marketing claims
- Permission to treat interface conformance as production fidelity
- Auto-merge of adversarial patches without review
- Changes to authorization, snapshot integrity, or security-boundary design
  labeled as good-first work

## How to engage before funding ops exist

1. Pick a track and open a GitHub discussion or issue using the roadmap field
   template.
2. Prefer offline reproduction from published release assets.
3. File defects via [report-environment-defect](../guides/report-environment-defect.md)
   and, when public, a registry PR under `registry/environment-defects/`.

## Related

- [ROADMAP.md](https://github.com/fraware/environment-assurance-compiler/blob/main/ROADMAP.md)
- [Benchmark charter](../governance/benchmark-charter.md)
- [Limitations](../research/limitations.md)
- [Good-first issues](good-first-issues/index.md)
