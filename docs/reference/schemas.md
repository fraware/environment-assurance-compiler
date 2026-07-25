# Schemas

Checked-in JSON Schema artifacts live under repository
[`schemas/`](https://github.com/fraware/environment-assurance-compiler/tree/main/schemas):

| File | Role |
| ---- | ---- |
| `world-0.2.0.json` | Write-current `WorldDefinition` schema |
| `world-0.1.0.json` | Frozen prior-stable schema (read window) |
| `world.json` | Alias of the write-current world schema |
| `pack-manifest.json` / `pack-manifest-1.json` | Environment pack manifest |

Export / refresh the current schema from Python:

```bash
python -c "from pathlib import Path; from envassure.ir.schema import export_schemas; export_schemas(Path('schemas'))"
```

Prior-stable files are not overwritten by export. See
[Compatibility](../compatibility.md) for the IR migrate policy (`eac migrate`).
