# Governance

Engineering-facing governance for EnvAssure. Funding, grant selection, and
payment operations are **out of band** for this repository.

## Surfaces

| Surface | Status | Notes |
| ------- | ------ | ----- |
| Compatibility policy | Live | [Compatibility](../compatibility.md) |
| Threat model / supply chain | Live | [Threat model](../security/threat-model.md), [Supply chain](../security/supply-chain.md) |
| Contribution / DCO / review | Landing with Milestone A | Root [CONTRIBUTING.md](https://github.com/fraware/environment-assurance-compiler/blob/main/CONTRIBUTING.md); [release process](../contributing/release-process.md) |
| CODEOWNERS / MAINTAINERS | Landing with Milestone A | Repository ops (owned by Milestone A agents) |
| [Benchmark charter](benchmark-charter.md) | Live (scaffolding) | Versioning rules for public packs |
| [GitHub Project fields](github-project-fields.md) | Template | Ops creates the board |
| [ROADMAP](https://github.com/fraware/environment-assurance-compiler/blob/main/ROADMAP.md) | Live (scaffolding) | Now / Next / Research / Later / Declined |
| Registries | Live (scaffolding) | [`registry/`](https://github.com/fraware/environment-assurance-compiler/tree/main/registry) — never auto-install plugins |
| [Good-first issues](../community/good-first-issues/index.md) | Drafts | §19 list; no auth/snapshot security-boundary starters |
| [Reproduction grant call](../community/reproduction-grant-call.md) | Call text only | No payment ops in-repo |

## Principles

1. Fail closed on unsupported semantics, missing extras, and absent evidence.
2. Explicit migrate only — never silent rewrite on lint, load, or verify-pack.
3. Interface conformance is not fidelity evidence.
4. Security-critical paths require reviewer attention (see release runbook).
5. Never silently modify a released benchmark version (see charter).

## Related

- [Community index](../community/index.md)
- [Release process](../contributing/release-process.md)
- [Defect reports](../contributing/defect-reports.md)
- [Release readiness 0.2](../research/release-readiness-0.2.md)
