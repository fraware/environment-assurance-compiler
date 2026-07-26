# EnvAssure

Documentation for the **Environment Assurance Compiler** (`envassure` / `eac`).

EnvAssure is a local-first toolchain that compiles operational evidence into
typed Environment IR, runs an event-sourced reference runtime, and produces
assurance artifacts (diagnostics, differential results, packs, reports).

!!! note "Public beta track"
    Package train is moving toward `0.2.0b1`. Working trees may still report a
    pre-beta `__version__`. APIs and IR minors can change; see
    [Compatibility](compatibility.md). Building a pack does **not** imply
    fidelity — see [Validation and fidelity](concepts/validation-and-fidelity.md).

## Version badge

| Contract | Value | Notes |
| -------- | ----- | ----- |
| Package (`envassure`) | toward `0.2.0b1` | See [`__version__`](https://github.com/fraware/environment-assurance-compiler/blob/main/src/envassure/__init__.py) in the checkout you installed |
| IR write-current | `0.2.0` | Read window includes prior stable `0.1.0` |
| Plugin API | `0.1.0` | Major must match compiler |
| Python | 3.11, 3.12, 3.13 | Requires-python `>=3.11` |
| Docs aliases (mike) | `/0.2.0b1/`, `/0.2/`, `/beta/` planned | `/stable/` reserved for a later stable cut |
| Last docs build | local / CI | Strict `mkdocs build`; versioned publish lands with release workflows |

### Integration status

| Integration | Status | Extra / pin | Docs |
| ----------- | ------ | ----------- | ---- |
| Gymnasium | Landing (Milestone C) | `[gym]` | [Gymnasium](integrations/gymnasium.md) |
| OPA obligations | Landing (Milestone C) | `[opa]` + system OPA binary | [OPA](integrations/opa.md) |
| Reference-system validation | Landing (Milestone C) | connector / compose | [Reference-system validation](integrations/reference-system-validation.md) |
| OpenEnv | Landing (Milestone C) | `[openenv]` pin TBD | [OpenEnv](integrations/openenv.md) |
| PettingZoo | Experimental | `[pettingzoo]` | Not a beta conformance track |

### Known limitations (docs honesty)

- Interface conformance is not production-fidelity evidence.
- Optional extras fail closed when absent; base wheel stays light.
- Benchmark packs and reproducibility bundles are Milestone D deliverables;
  pages describe the intended contract before artifacts ship.
- See [Limitations](research/limitations.md) and
  [Release readiness 0.2](research/release-readiness-0.2.md).

## Documentation map

| Section | Contents |
| ------- | -------- |
| [Getting started](getting-started.md) | Install, workspace, first build |
| [Ten-minute tutorial](guides/ten-minute-tutorial.md) | Counter example end-to-end |
| Concepts | Sources, IR, ambiguities, runtime, fidelity |
| Integrations | OpenEnv, Gymnasium, OPA, reference-system validation |
| Guides | Workflows, fidelity claims, author stubs, defect reporting |
| Reference | SDK, CLI, schemas, diagnostics, exit codes, plugins |
| Packs / repro | [Benchmark packs](packs/benchmark-packs.md), [Reproducibility](reproducibility.md) |
| [Security](security/threat-model.md) | Threat model; [supply chain](security/supply-chain.md) |
| Research | Methodology, benchmarks, limitations, [0.2 release readiness](research/release-readiness-0.2.md) |
| [Governance](governance/index.md) | Engineering governance surfaces |
| [Compatibility](compatibility.md) | Contracts, deprecation, cadence |
| [Release notes](release-notes.md) | Changelog pointer |
| [Contributing](contributing.md) | Contribution entry and guides |

Repository: [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)  
License: Apache-2.0
