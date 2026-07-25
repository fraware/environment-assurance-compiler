# Published JSON Schema artifacts

Checked-in schemas for Environment IR and Environment Pack manifests.

| File | Role |
| ---- | ---- |
| `world-0.2.0.json` | Write-current `WorldDefinition` (`ir_version` 0.2.0) |
| `world-0.1.0.json` | Frozen prior-stable schema (read window) |
| `world.json` | Alias of the write-current world schema |
| `pack-manifest.json` / `pack-manifest-1.json` | Pack manifest schema |

Regenerate the current world schema:

```bash
python -c "from pathlib import Path; from envassure.ir.schema import export_schemas; export_schemas(Path('schemas'))"
```

Prior-stable files are preserved. Compatibility and migrate policy:
[`docs/compatibility.md`](../docs/compatibility.md).
