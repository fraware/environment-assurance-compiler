# Ten-minute tutorial

Goal: from a clean checkout to a linted IR, a short runtime run, and a verified
pack — using the built-in counter example. Expect about ten minutes on a laptop
with Python 3.11+.

For a shorter install-only path, see [Getting started](../getting-started.md).

## 1. Install (≈2 min)

```bash
python -m pip install -e ".[dev]"
eac --version
eac doctor
```

Optional docs later: `pip install -e ".[docs]"` then `mkdocs serve`.

## 2. Build and lint IR (≈3 min)

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json --force
eac lint examples/counter/ir/world.json
```

Success means the document is well-formed enough to inspect — **not** production
parity. See [Fidelity claims](fidelity-claims.md).

## 3. Run and check determinism (≈3 min)

```bash
eac run examples/counter/ir/world.json -a increment,increment
eac test examples/counter/ir/world.json -a increment,reset,increment
```

`eac test` checks that identical action sequences yield identical digests under
reset. Failures are diagnostics, not silent mismatches.

## 4. Package and verify (≈2 min)

```bash
eac package examples/counter/ir/world.json -o /tmp/counter.eap
eac verify-pack /tmp/counter.eap
```

Packs remain untrusted until verified. Do not treat a green verify as a fidelity
certificate.

## What you just exercised

| Step | Surface |
| ---- | ------- |
| Manual SDK → IR | `World` authoring + `eac build-ir` |
| Static checks | `eac lint` |
| Reference runtime | `eac run` / `eac test` |
| Assurance pack | `eac package` / `eac verify-pack` |

## Next paths

- Import evidence: [Build from OpenAPI](build-from-openapi.md)
- Differential probes: [Differentially validate](differentially-validate.md)
- Extend the toolchain: [Author plugins](author-plugins.md),
  [Author a source adapter](author-source-adapter.md),
  [Author a runtime extension](author-runtime-extension.md)
- Honest scoping: [Limitations](../research/limitations.md),
  [Release readiness 0.2](../research/release-readiness-0.2.md)
