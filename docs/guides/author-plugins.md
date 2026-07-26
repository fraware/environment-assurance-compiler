# Author plugins

Plugins extend EnvAssure without forking the core. Normative contracts live in
[Plugin API](../reference/plugin-api.md) and ADR-0004; this page is the author
quick-start.

## Quick start

```bash
eac plugins create my-plugin --kind source_adapter
eac plugins test path/to/plugin
eac plugins package path/to/plugin -o my-plugin.zip
eac plugins doctor
```

Pin and allowlist plugins for release builds (`.eac/plugin-lock.json`,
`eac plugins doctor --enforce-allowlist`).

## Contracts to respect

| Contract | Rule |
| -------- | ---- |
| `plugin_api_version` | Major mismatch → fail closed (`EAC9006`) |
| Kinds | `source_adapter`, `codegen_target`, proposal providers, etc. — see Plugin API |
| Proposal providers | Entry point group `envassure.proposal_providers`; never authoritative without expert review |
| Trust | Plugin code is executable supply-chain risk; digests belong in the lockfile |

## Validation profiles

When a plugin emits facts or IR fragments, keep validation profiles honest:

- **Executable** profiles reject unsupported observation semantics
  (`compile_observation(..., strict_unsupported=True)`).
- Differential / CEGR four-state verdicts must not collapse `indeterminate`
  into match.
- Release packs still require reconciled ambiguities (`eac decide`).

Pre-alpha: expect API churn under the
[compatibility policy](../compatibility.md). Prefer contributing upstream
adapters over long-lived private forks until `plugin_api_version` reaches a
stable channel.
