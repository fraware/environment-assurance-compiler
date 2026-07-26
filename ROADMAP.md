# EnvAssure roadmap

Public engineering roadmap for `envassure` / `eac`. Buckets are priority
signals, not calendar commitments. Do **not** treat dates as delivery promises
without an assigned owner and resourced acceptance criteria.

Funding, grant selection, and payment operations are out of band. See the
[reproduction grant call](docs/community/reproduction-grant-call.md) for the
engineering call text only.

## Issue field template

Every roadmap item must link to a GitHub issue that fills **all** of these
fields (also mirrored on the public Project board — see
[GitHub Project field template](docs/governance/github-project-fields.md)):

| Field | Purpose |
| ----- | ------- |
| **Problem** | What is broken, missing, or under-specified? |
| **Intended claim** | What may we assert after this lands? What remains out of claim? |
| **Deliverable** | Concrete artifacts (code, schema, docs, pack, workflow). |
| **Owner** | Named maintainer or area (`CODEOWNERS` path). |
| **Dependencies** | Blocking issues, extras, upstream pins. |
| **Acceptance test** | Commands / CI jobs that must pass. |
| **Compatibility impact** | IR / plugin API / pack / CLI surface changes. |
| **Status** | `proposed` \| `accepted` \| `in_progress` \| `blocked` \| `done` \| `declined` |

Labels: use roadmap bucket labels (`roadmap:now`, `roadmap:next`,
`roadmap:research`, `roadmap:later`, `roadmap:declined`) plus area labels.

---

## Now

Work required for a coherent public beta (`0.2.0b1`) once Milestones A–D are
green. Tracking issues land as release gates close; placeholders below name the
intended claim.

| Item | Intended claim | Status |
| ---- | -------------- | ------ |
| Signed-tag release train (PyPI + GHCR + manifest + SBOM) | Installable, cryptographically attributable beta artifacts | `in_progress` (Milestone A) |
| Versioned docs (`mike`) + example contract E1–E5 | Docs and examples run from released wheel / image | `in_progress` (Milestone B) |
| Reference integrations (Gymnasium, OPA, HTTP+PG connector, OpenEnv) | Documented support status with conformance commands | `in_progress` (Milestone C) |
| Three benchmark packs + reproducibility bundle | Packs lint/verify; bundle verifies without source checkout | `in_progress` (Milestone D) |
| Community registries + good-first issues + governance charter | Engineering-only community surfaces public | `in_progress` (Milestone E scaffolding) |

Open GitHub issues for each row before treating the row as a commitment.

---

## Next

Post-beta hardening that does not block `0.2.0b1` cut, once A–D are green.

| Item | Intended claim | Notes |
| ---- | -------------- | ----- |
| PettingZoo conformance track | Experimental → qualified (or remain experimental with explicit non-claim) | Separate from Gymnasium |
| First curated plugin-registry entries | Metadata-only discovery; never auto-install | [`registry/plugins-v1.json`](registry/plugins-v1.json) |
| Environment-defect intake → registry records | Public defects with digests and residual limitations | [`registry/environment-defects/`](registry/environment-defects/) |
| Docs / release CI good-first issues (§19) | Contributor-sized quality gates | [`docs/community/good-first-issues/`](docs/community/good-first-issues/) |
| Stable docs alias `/stable/` | Reserved until a stable (non-beta) release | Do not point at `b1` |

---

## Research

Methodological and empirical work. Results must keep dimensions separate and
publish negative results.

| Item | Intended claim | Notes |
| ---- | -------------- | ----- |
| Hidden-reference pack challenges | Independent reproduction of concealed suites | Grant call track 2 |
| Adversarial assurance-claim challenges | Defects against overstated claims | Grant call track 3 |
| Ablations by evidence class | Which diagnostic families fire when evidence drops | [Methodology](docs/research/methodology.md) |
| Contamination / custody drills for packs | Benchmark charter operationalization | [Benchmark charter](docs/governance/benchmark-charter.md) |

---

## Later

Useful, not scheduled.

| Item | Notes |
| ---- | ----- |
| OCI distribution of benchmark packs | Packs are GitHub Release assets for beta |
| Additional reference connectors beyond refund HTTP+PG | After C3 patterns stabilize |
| Model-assisted proposal UX beyond current providers | Keep non-authoritative |
| Multi-language codegen targets | Plugin / codegen contribution path |

---

## Declined

Explicit non-goals for the public beta window. Reopen only with a new issue that
revisits the intended claim.

| Item | Reason |
| ---- | ------ |
| Operating or funding reproduction grants in-repo | Engineering call text only; payment out of band |
| Auto-install / auto-enable of registry plugins | Supply-chain fail-closed; curated metadata only |
| Composite single-number fidelity leaderboard | Violates multi-dimensional reporting ([ADR-0005](adrs/0005-fidelity-profile.md)) |
| Silent IR repair / migrate on lint or verify-pack | Explicit `eac migrate` only |
| Claiming production behavioral parity from `build-ir` alone | Facts ≠ finished high-fidelity world |
| Treating PettingZoo as release-qualified in `0.2.0b1` | Experimental until own conformance track |

---

## Related

- [Governance index](docs/governance/index.md)
- [Benchmark charter](docs/governance/benchmark-charter.md)
- [Release readiness 0.2](docs/research/release-readiness-0.2.md)
- [Limitations](docs/research/limitations.md)
