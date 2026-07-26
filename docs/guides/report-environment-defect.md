# How to report an environment defect

An **environment defect** is a fidelity or semantics gap between an EnvAssure
world (IR + runtime behavior + declared claims) and the real system it models —
not a generic compiler crash.

Security vulnerabilities in the toolchain itself use private disclosure
([SECURITY.md](https://github.com/fraware/environment-assurance-compiler/blob/main/SECURITY.md)),
not public issues.

## When to use this process

- Missing timeout / retry / auth / failure modes that production exhibits
- Differential probes that mismatch for a documented reason
- Ambiguous imports that were closed incorrectly
- Overstated fidelity claims relative to available evidence

Compiler bugs, docs typos, and CLI failures use the **Bug report** issue
template instead.

## What to include

1. **Environment ids** — IR path, `environment_id`, package / commit SHA.
2. **Systems under comparison** — production or reference surface and version.
3. **Evidence class** — direct, observed, inferred, or expert (with decision id).
4. **Minimal probe** — actors, actions, payloads, expected vs actual; prefer
   offline fixtures.
5. **Impact** — which claims become unsafe if left open.

Use the GitHub **Environment defect** issue template under
`.github/ISSUE_TEMPLATE/`.

## Suggested workflow inside EnvAssure

```bash
# Capture differential or runtime evidence offline when possible
eac differential …   # fixture / simulator preferred
eac refine …         # CEGR intake when counterexamples exist
eac ambiguities --path .
# Record expert interpretation rather than silent repair
eac decide <ambiguity-id> --interpretation … --rationale …
```

Do not “fix” fidelity by deleting indeterminate dimensions from reports.

## Related

- [Fidelity claims](fidelity-claims.md)
- [Ambiguities and decisions](../concepts/ambiguities-and-decisions.md)
- [Limitations](../research/limitations.md)
