# Release notes

EnvAssure uses [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
Semantic Versioning for the compiler package. IR schema, plugin API, pack
format, and codegen templates are versioned separately — see
[Compatibility](compatibility.md).

## Authoritative changelog

The full history lives in the repository root
[`CHANGELOG.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/CHANGELOG.md).

## Public beta train (`0.2.0b1`)

| Milestone | Theme | Docs status |
| --------- | ----- | ----------- |
| A | Release foundation (PyPI, workflows, manifest, container) | Ops runbook: [Release process](contributing/release-process.md) |
| B | Docs IA, example contract, contribution guides | This documentation set |
| C | Gymnasium, OPA, reference connector, OpenEnv | [Integrations](integrations/openenv.md) pages are honest stubs until qualify |
| D | Benchmark packs + reproducibility bundle | [Benchmark packs](packs/benchmark-packs.md), [Reproducibility](reproducibility.md) |
| E | Community scaffolding + cut `v0.2.0b1` | [Governance](governance/index.md) |

Until `v0.2.0b1` is tagged, treat package metadata and docs aliases as
**pre-release**. Do not claim PyPI / GHCR / mike `/beta/` coordinates until the
release workflow publishes them.

## Related

- [Unreleased notes in CHANGELOG](https://github.com/fraware/environment-assurance-compiler/blob/main/CHANGELOG.md)
- [Release readiness 0.2](research/release-readiness-0.2.md)
- [Limitations](research/limitations.md)
