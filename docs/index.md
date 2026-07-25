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
| Concepts | Sources, IR, ambiguities, runtime, fidelity |
| Guides | Runnable end-to-end workflows |
| Reference | SDK, CLI, schemas, diagnostics, exit codes, plugins |
| [Security](security/threat-model.md) | Threat model |
| Research | Methodology, benchmarks, limitations |
| [Contributing](contributing.md) | Contribution entry |

Repository: [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)  
License: Apache-2.0
