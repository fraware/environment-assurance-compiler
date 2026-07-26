# Package and publish

Environment Packs (`.eap`) are checksummed archives of canonical IR plus related
artifacts. Format **v2** is write-current. This guide uses `examples/counter/`.

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

Optional first-class inputs:

```bash
eac package examples/counter/ir/world.json -o counter.eap \
  --fidelity ledger.json \
  --sources-manifest sources.yml \
  --migration-history migration.json \
  --signature detached.sig \
  --workspace .
```

Every pack embeds (format v2 required members):

| Member | Role |
| --- | --- |
| `ir/world.json` | Canonical world IR |
| `schemas/world-*.json` + `schemas/world.json` | Write-current world schema |
| `schemas/pack-manifest-2.json` + alias | Pack manifest schema |
| `sources/manifest.json` | Source digests (`sources.yml` or world semantic ids) |
| `provenance/bundle.json` | Flattened IR provenance + decision links |
| `migration/history.json` | Migrate chain applied (identity when none) |
| `compatibility.json` | Supported pack/IR read window |
| `fidelity/ledger.json` | Scoped fidelity claims (no aggregate score) |
| `manifest.json` | `format_version`, `runtime_version`, `policy_version`, per-file hashes, `content_digest` |
| `signatures/` | Optional detached signature blobs (integrity-checked: manifest listing, per-file SHA-256, and `metadata.signatures` inventory / `signed_content_digest`; cryptographic key verification is out of band) |

Secret-like payloads are rejected at pack time (fail closed).

## 3. Verify before distribution

```bash
eac verify-pack counter.eap --json
```

Pass criteria:

- Exit code `0`
- Message `Pack OK`
- No `EAC8006` diagnostics
- Format version inside the supported read window; required members present;
  IR + fidelity ledger parse; checksums match; optional `signatures/` members
  match manifest listings and `metadata.signatures` digests (integrity only)

Re-verify after any transfer; digests must match.

## 4. Assurance report (optional)

```bash
eac report examples/counter/ir/world.json -o reports/counter --fidelity ledger.json --json
```

Reports treat the fidelity ledger as the source of truth for sections §20.3 /
§20.4. They are derived from canonical IR digests and are not a substitute for
`verify-pack`.

## 5. Versioning guidance

1. Bump `WorldDefinition.version` (and `environment_id` when semantics change).
2. Rebuild IR → re-lint → re-analyze → re-package → re-verify.
3. Record open ambiguities / expert decisions before claiming release grade.
4. Keep `ir_version` aligned with the installed `envassure` IR schema.
5. Pack `format_version` is independent of IR version; see
   [compatibility](../compatibility.md).

## 6. Publish (local hand-off)

EnvAssure does not push remotes for you. A typical hand-off:

```bash
eac verify-pack counter.eap
# Copy counter.eap plus the matching git tag / lock digests to your artifact store.
```

Consumers should run `eac verify-pack` before loading IR from the archive.

For compiler package releases (wheels / sdist), see
[supply chain](../security/supply-chain.md) for CycloneDX SBOM assets and
GitHub build-provenance verification (`gh attestation verify`).

## Checklist

| Step | Command | Fail closed on |
| --- | --- | --- |
| Build | `eac build-ir` | Module/IR errors |
| Lint | `eac lint` | `EAC3xxx` |
| Analyze | `eac analyze` | Unexpected `EAC4xxx`/`EAC5xxx` for release |
| Package | `eac package` | Secrets / missing v2 inputs / IO errors |
| Verify | `eac verify-pack` | Digest / format window / ledger / secret scan (`EAC8006`) |
