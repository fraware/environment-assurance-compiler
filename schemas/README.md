# Published JSON Schema artifacts

Checked-in schemas for Environment IR, Environment Pack manifests, and compiler
release manifests.

| File | Role |
| ---- | ---- |
| `world-0.2.0.json` | Write-current `WorldDefinition` (`ir_version` 0.2.0) |
| `world-0.1.0.json` | Frozen prior-stable schema (read window) |
| `world.json` | Alias of the write-current world schema |
| `pack-manifest-2.json` / `pack-manifest.json` | Write-current pack manifest (`format_version` 2) |
| `pack-manifest-1.json` | Frozen prior pack manifest schema |
| `release-manifest-1.json` | Compiler release manifest (§4.3) — digests and coordinates |

Regenerate the current world schema:

```bash
python -c "from pathlib import Path; from envassure.ir.schema import export_schemas; export_schemas(Path('schemas'))"
```

Generate a release manifest (after `python -m build`):

```bash
python scripts/generate_release_manifest.py \
  --dist-dir dist \
  --tag v0.2.0.dev0 \
  --commit "$(git rev-parse HEAD)" \
  --out dist/release-manifest.json
```

Prior-stable files are preserved. Compatibility and migrate policy:
[`docs/compatibility.md`](../docs/compatibility.md). Release process:
[`docs/contributing/release-process.md`](../docs/contributing/release-process.md).
