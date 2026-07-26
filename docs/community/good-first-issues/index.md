# Good-first issue drafts (§19)

Seed drafts for maintainers to file as GitHub issues (`good first issue` label).
Each draft specifies **files**, **tests**, **non-goals**, and **reviewer**.

Do not use this list for authorization, snapshot integrity, or security-boundary
redesign work.

| ID | Title | Reviewer (area) |
| -- | ----- | --------------- |
| [GFI-01](01-docs-link-checker.md) | Docs-link checker | Docs / CI (`docs/**`, `.github/workflows/docs*`) |
| [GFI-02](02-release-manifest-validator.md) | Release-manifest validator | Packaging / release |
| [GFI-03](03-gymnasium-enum-codec-tests.md) | Gymnasium enum codec tests | Runtime adapters |
| [GFI-04](04-example-manifest-linter.md) | Example-manifest linter | Docs / examples |
| [GFI-05](05-plugin-registry-schema.md) | Plugin-registry schema CI + contribution path | Plugins / supply chain |
| [GFI-06](06-opa-evidence-schema.md) | OPA evidence schema | Obligations / integrations |
| [GFI-07](07-connector-timeout-fixture.md) | Connector timeout fixture | Differential / connectors |
| [GFI-08](08-shell-completion-docs.md) | Shell-completion docs | CLI / docs |
| [GFI-09](09-benchmark-card-template.md) | Benchmark-card template | Benchmarks |
| [GFI-10](10-reproducibility-verifier.md) | Reproducibility verifier | Repro / release |
| [GFI-11](11-diagnostic-documentation-generator.md) | Diagnostic documentation generator | Diagnostics |
| [GFI-12](12-windows-pack-path-regression.md) | Windows pack-path regression | Packaging / Windows CI |

When filing on GitHub, copy the draft body and add roadmap fields from
[ROADMAP.md](https://github.com/fraware/environment-assurance-compiler/blob/main/ROADMAP.md).
