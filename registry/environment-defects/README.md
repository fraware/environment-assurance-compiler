# Environment defect registry

Public fidelity / semantics defect records for EnvAssure environments and packs.
Security vulnerabilities in the toolchain use private disclosure
([SECURITY.md](../../SECURITY.md)), not this tree.

## Layout

| Path | Role |
| ---- | ---- |
| [`TEMPLATE.yaml`](TEMPLATE.yaml) | Copy when filing a new public record |
| [`ENV-YYYY-NNNN.yaml`](ENV-2026-0001.yaml) | Assigned records |
| [`../../schemas/environment-defect-v1.schema.json`](../../schemas/environment-defect-v1.schema.json) | JSON Schema (YAML must validate when loaded as JSON-compatible data) |

## ID assignment

`ENV-YYYY-NNNN` — calendar year of disclosure preparation, zero-padded sequence
starting at `0001` per year. Maintainers assign IDs; do not self-allocate in PRs
without coordination.

## Required fields (summary)

See schema. Normative list from the public-beta specification:

- affected pack or environment
- versions and digests
- discoverer
- severity and class
- reproducer
- observed and expected behavior
- affected claims
- disclosure status
- fixed version
- permanent regression
- residual limitation
- linked issues and releases

Keep security-sensitive records private until disclosure.

## Related

- [Report an environment defect](../../docs/guides/report-environment-defect.md)
- [Fidelity claims](../../docs/guides/fidelity-claims.md)
- Issue template: `.github/ISSUE_TEMPLATE/environment_defect.md`
