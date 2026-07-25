# EnvAssure

Documentation for the **Environment Assurance Compiler** (`envassure` / `eac`).

EnvAssure is a local-first toolchain that compiles operational evidence into
typed Environment IR, runs an event-sourced reference runtime, and produces
assurance artifacts (diagnostics, differential results, packs, reports).

**Status:** pre-alpha. APIs and IR minors may change; see
[Compatibility](compatibility.md). Building a pack does **not** imply fidelity —
see [Validation and fidelity](concepts/validation-and-fidelity.md).

## Documentation map

| Section | Contents |
| ------- | -------- |
| [Getting started](getting-started.md) | Install, workspace, first build |
| [Ten-minute tutorial](guides/ten-minute-tutorial.md) | Counter example end-to-end |
| Concepts | Sources, IR, ambiguities, runtime, fidelity |
| Guides | Workflows, fidelity claims, author stubs, defect reporting |
| Reference | SDK, CLI, schemas, diagnostics, exit codes, plugins |
| [Security](security/threat-model.md) | Threat model; [supply chain](security/supply-chain.md) |
| Research | Methodology, benchmarks, limitations, [0.2 release readiness](research/release-readiness-0.2.md) |
| [Compatibility](compatibility.md) | Contracts, deprecation, cadence |
| [Contributing](contributing.md) | Contribution entry |

Repository: [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)  
License: Apache-2.0
