# Benchmark governance charter

Charter for public EnvAssure benchmark packs, concealed suites, and published
reproduction assets. This is an engineering governance document: it does not
authorize funding or grant payment.

## Purpose

Ensure benchmark changes are reviewable, versioned, free of silent semantic
drift, and honest about what a passing run means (dimension-separated metrics;
not a composite fidelity leaderboard).

## Roles

| Role | Responsibility |
| ---- | -------------- |
| **Pack maintainers** | Own pack layout, `pack.yaml`, baselines, mutation suites, release artifacts |
| **External reviewers** | Independent review of construct validity, hidden-test custody, and claim wording |
| **Domain experts** | Domain-specific judgment (payments, auth, stochastic ops) recorded with rationale |
| **Release engineers** | Wire signed release assets, digests, and reproduction workflows |

Conflicts of interest (employment, competing products, prior authorship of a
challenged claim) must be disclosed on proposals and reviews. Conflicted
reviewers may advise but do not sole-approve hidden-reference changes.

## Proposals

Benchmark changes enter via GitHub issue + PR using the roadmap field template
([github-project-fields.md](github-project-fields.md)):

1. Problem and intended claim (including non-claims)
2. Deliverable and acceptance tests
3. Compatibility / version impact (see versioning below)
4. Contamination risk assessment

Hidden-reference material must not appear in public PR diffs. Use maintainer
custody channels described under **Hidden-test custody**.

## Hidden-test custody

- Oracle digests and concealed generators may ship as code; full answer keys
  that trivialize the suite must not be the only evaluation path.
- Access to unpublished adversarial fixtures requires maintainer approval and
  logging of who accessed what, when.
- CI may run capped public probes; uncapped / custody suites run on scheduled
  or release workflows with least privilege.

## Versioning

Never silently modify a released benchmark version. Bump according to:

| Bump | When |
| ---- | ---- |
| **Major** | Changed construct, hidden reference, or primary metric |
| **Minor** | Compatible task or probe additions |
| **Patch** | Correction preserving intended semantics |

Additional rules:

1. Released pack versions are immutable: new content ⇒ new version + new digests.
2. Metric renames or dimension merges are **major** (they change primary interpretation).
3. Seed changes that alter oracle digests are **major** unless proven bit-identical.
4. Documentation-only clarifications that do not change probes may be **patch**.
5. Deprecations require a residual-limitation note and a successor version pointer.

## Appeals

Challenges to scoring, custody, or claim wording:

1. File a public issue with evidence (logs, digests, environment record).
2. Pack maintainers respond with accept / reject / indeterminate and rationale.
3. Escalation: second maintainer + one external reviewer for major-version disputes.
4. Outcomes are recorded in public minutes (or linked issue comments for beta).

## Contamination

Treat as contamination:

- Publishing hidden oracles that trivialize evaluation
- Training or tuning against concealed suites when claiming independent reproduction
- Editing released artifacts in place

Mitigations: version pins, digests in release manifests, reproduction bundles that
verify without source checkout, and grant-call methodological scoring that
rewards disclosure of contamination risk.

## Deprecation

Deprecated packs remain downloadable with clear banners: version, successor,
and why results are no longer comparable. Do not delete released assets that
appear in published papers or grant reports without a tombstone record.

## Incidents

Integrity incidents (leak of hidden tests, digest mismatch on release assets,
silent metric change):

1. Freeze affected version promotion
2. Disclose impact and residual limitations
3. Ship a corrected **new** version (never silent rewrite)
4. Add permanent regression checks when applicable

## Public minutes

For beta: Project board notes and linked issues suffice. Post-beta, publish
short meeting notes for major/minor pack version decisions under
`docs/governance/` or linked discussions.

## Related

- [Benchmarks (docs)](../research/benchmarks.md)
- [Methodology](../research/methodology.md)
- [ROADMAP.md](https://github.com/fraware/environment-assurance-compiler/blob/main/ROADMAP.md)
- [Reproduction grant call](../community/reproduction-grant-call.md)
