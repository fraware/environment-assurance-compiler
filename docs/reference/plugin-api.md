# Plugin API

Plugins extend EnvAssure without forking the core
([ADR-0004](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0004-plugin-edges.md)).

## Version

Current `plugin_api_version`: **`0.1.0`** (`envassure.plugins.PLUGIN_API_VERSION`).
Major mismatches fail closed with `EAC9006`.

## Kinds

| Kind | Role |
| ---- | ---- |
| `generic` | Minimal register metadata |
| `source_adapter` | Custom import adapters |
| `codegen_target` | Code-generation targets |

## CLI

```bash
eac plugins list
eac plugins create my-plugin --kind source_adapter
eac plugins test path/to/plugin
eac plugins package path/to/plugin -o my-plugin.zip
eac plugins doctor
eac plugins doctor --enforce-allowlist
```

Release mode should pin discovered plugins in `.eac/plugin-lock.json` and enforce
an allowlist. Untrusted plugins must not become defaults in release builds.

## Python surface

```python
from envassure.plugins import (
    PLUGIN_API_VERSION,
    PluginSpec,
    create_plugin_scaffold,
    validate_plugin,
    discover_plugins,
    doctor_plugins,
    check_allowlist,
)
```

Entry-point group for proposal providers (separate from filesystem plugins):
`envassure.proposal_providers` (see `pyproject.toml`).

## Security notes

- Treat plugin code as executable supply-chain risk.
- Prefer allowlists + pinned digests over open discovery in release CI.
- See the [threat model](../security/threat-model.md).
