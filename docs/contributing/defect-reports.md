# Defect reports

When something looks wrong, choose the right disclosure path.

## Paths

| Kind | Where |
| ---- | ----- |
| Environment defect (fidelity / semantics gap) | Public **Environment defect** issue template; guide [Report environment defect](../guides/report-environment-defect.md) |
| Compiler / CLI / docs bug | Public **Bug report** template |
| Security vulnerability in the toolchain | Private disclosure per [SECURITY.md](https://github.com/fraware/environment-assurance-compiler/blob/main/SECURITY.md) |

## Environment defect minimums

1. Environment ids (IR path, `environment_id`, package / commit).
2. Systems under comparison and versions.
3. Evidence class (direct, observed, inferred, expert).
4. Minimal offline probe when possible.
5. Impact on declared fidelity claims.

Do not file environment defects for undisclosed security issues in the
compiler itself.

## Related

- [Fidelity claims](../guides/fidelity-claims.md)
- [Validation and fidelity](../concepts/validation-and-fidelity.md)
- [Governance](../governance/index.md)
