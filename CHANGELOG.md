# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
for the compiler package. IR schema, plugin API, pack format, and codegen templates
are versioned separately (see [compatibility policy](docs/compatibility.md)).

## [Unreleased]

### Added

- IR `0.2.0` write-current schema with explicit `0.1.0` → `0.2.0` migrate
  transforms (`assurance_profile`, normalized `state_model_version`, optional
  `profile` rename). Read window is the last two stable minors.
- `[postgres]` extra (`psycopg`): Postgres DDL adapter + opt-in
  `PostgresReferenceConnector` (offline-testable via stubs).
- `[model-assisted]` extra (`httpx`): HTTP proposal provider packaging with
  stub default; fail-closed when a non-stub provider is requested without the
  extra.
- Release-oriented documentation pass (README, guides, diagnostic catalog,
  threat model, MkDocs nav aligned to §25.1).
- Release-readiness baseline for 0.2 RC (`docs/research/release-readiness-0.2.md`),
  adoption guides (ten-minute tutorial, fidelity claims, environment-defect
  reporting, plugin/source/runtime author stubs), and GitHub issue templates.
- CI expansion: Python 3.11–3.13 matrix, sdist/wheel clean install, coverage
  XML artifact, strict MkDocs build, schema/fixture checks, counter example
  E2E, CodeQL, blocking `pip-audit`, extras import matrix, offline benchmark
  regression, Gitleaks secret scan, advisory CycloneDX SBOM preview.
- Coverage fail-under gates: overall **75%**, cores (omit CLI/adapters/tasks)
  **80%**, assurance packages **80%**, semantic cores **90%**
  (`.coveragerc.semantic`).
- Schedule workflow `nightly-empirical.yml` for full concealed benchmarks
  (CI PRs keep `--max-probes 20`).
- Release workflow: wheel/sdist build, CycloneDX SBOM assets, GitHub OIDC
  build-provenance attestations (`actions/attest-build-provenance`).
- Docs: [supply chain](docs/security/supply-chain.md) verification guide;
  author guides for plugins / source adapters / runtime extensions.

### Changed

- Workspace default `ir_version` and counter example IR updated to `0.2.0`.
- Compatibility doc extended with deprecation policy and release-cadence pointer.

### Release cadence

Pre-alpha trains are **milestone-driven** (remediation R00–R17 toward
`0.2.0rc`), not a fixed calendar. Notable package versions are tagged and
described in this changelog. After the first stable channel:

- **Patch** — bugfixes and security fixes; no intentional contract breaks.
- **Minor** — additive IR/plugin/pack features within the compatibility window;
  deprecations announced here before removal.
- **Major** — breaking contract changes when on a stable channel.

Yanked or broken releases are called out explicitly in this file.

## [0.1.0a0] — 2026-07-25

### Added

- Phase 0: package layout, CLI `eac`, fail-closed stubs, diagnostics, canonical
  JSON, workspace init/doctor/locks, ADRs, threat model, CI, docs skeleton.
- Phase 1: `WorldDefinition` IR, JSON Schema export, manual SDK (`World`,
  decorators), `eac build-ir|lint|diff|explain|generate`, counter + auth examples.
- Phase 2: OpenAPI/DB/policy/procedure/trace adapters, SemanticFact store,
  reconciliation, ambiguities/decide, refund conflict example.
- Phase 3: Event-sourced runtime (reset/step/snapshot/restore/fork), codegen,
  Gymnasium/PettingZoo lazy adapters, `eac run|snapshot|replay|test`.
- Phase 4: Static analyses, coverage, mutation, tasks/verifiers helpers,
  inventory stochastic example, `eac analyze|coverage`.
- Phase 5: Reference connectors, probe planner, differential compare, CE
  minimization, `eac differential`.
- Phase 6–7: `.eap` packs + secret scan, assurance-case JSON/HTML, plugin SDK
  CLI, model-assisted proposals (non-authoritative), offline benchmarks,
  `eac package|verify-pack|report|plugins|benchmark|refine`.
- Depth tightening: dataflow reachability + `EAC4009`/`EAC4010`,
  file-backed/subprocess connectors, ≥100-probe expansion, stub proposal
  provider + review disposition pipeline.
