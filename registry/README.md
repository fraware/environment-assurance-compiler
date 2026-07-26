# EnvAssure registries

Checked-in curated metadata. These registries are **not** installers.

| Path | Role |
| ---- | ---- |
| [`plugins-v1.json`](plugins-v1.json) | Plugin discovery metadata (schema-validated) |
| [`environment-defects/`](environment-defects/) | Public environment-defect records |

## Hard rules

1. **Never auto-install** or auto-enable registry plugins from CLI or CI.
2. Plugin code remains supply-chain risk; require allowlists + digests for release builds ([Plugin API](../docs/reference/plugin-api.md)).
3. Security-sensitive environment defects stay private until coordinated disclosure ([SECURITY.md](../SECURITY.md)).
4. Schema sources of truth live under [`schemas/`](../schemas/).

## Validate (once tooling lands)

```bash
# Example — contributors may wire this in CI (good-first issue GFI-05)
python -c "import json, jsonschema, pathlib; \
  schema=json.loads(pathlib.Path('schemas/plugin-registry-v1.schema.json').read_text()); \
  data=json.loads(pathlib.Path('registry/plugins-v1.json').read_text()); \
  jsonschema.validate(data, schema)"
```

See also [ROADMAP.md](../ROADMAP.md) and [governance](../docs/governance/index.md).
