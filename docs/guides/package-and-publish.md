# Package and publish

Environment Packs (`.eap`) are checksummed archives of canonical IR plus related
artifacts. This guide uses `examples/counter/`.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## 1. Build canonical IR

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
```

Fix any `EAC3xxx` reference errors before packaging. For release packs, also run:

```bash
eac analyze examples/counter/ir/world.json
eac test examples/counter/ir/world.json
```

## 2. Create the pack

```bash
eac package examples/counter/ir/world.json -o counter.eap --json
```

The pack embeds:

- `ir/world.json` (canonical)
- Manifest with `content_digest` / environment id / tool versions
- Optional extra members when using the Python API

Secret-like payloads are rejected at pack time (fail closed).

## 3. Verify before distribution

```bash
eac verify-pack counter.eap --json
```

Pass criteria:

- Exit code `0`
- Message `Pack OK`
- No `EAC8006` diagnostics

Re-verify after any transfer; digests must match.

## 4. Assurance report (optional)

```bash
eac report examples/counter/ir/world.json -o reports/counter --json
```

Reports are derived from canonical IR digests and are not a substitute for
`verify-pack`.

## 5. Versioning guidance

1. Bump `WorldDefinition.version` (and `environment_id` when semantics change).
2. Rebuild IR → re-lint → re-analyze → re-package → re-verify.
3. Record open ambiguities / expert decisions before claiming release grade.
4. Keep `ir_version` aligned with the installed `envassure` IR schema.

## 6. Publish (local hand-off)

EnvAssure does not push remotes for you. A typical hand-off:

```bash
eac verify-pack counter.eap
# Copy counter.eap plus the matching git tag / lock digests to your artifact store.
```

Consumers should run `eac verify-pack` before loading IR from the archive.

## Checklist

| Step | Command | Fail closed on |
| --- | --- | --- |
| Build | `eac build-ir` | Module/IR errors |
| Lint | `eac lint` | `EAC3xxx` |
| Analyze | `eac analyze` | Unexpected `EAC4xxx`/`EAC5xxx` for release |
| Package | `eac package` | Secrets / IO errors |
| Verify | `eac verify-pack` | Digest / schema / secret scan (`EAC8006`) |
