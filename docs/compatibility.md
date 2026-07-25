# Compatibility Policy

EnvAssure versions several contracts independently:

| Contract              | Identifier              | Compatibility rule                                      |
| --------------------- | ----------------------- | ------------------------------------------------------- |
| Compiler package      | `envassure` PyPI ver.   | SemVer                                                  |
| IR schema             | `ir_version`            | Read last two stable minors; write current              |
| Plugin API            | `plugin_api_version`    | Breaking changes require major bump                     |
| Environment Pack      | pack format version     | Older packs verify if within supported window           |
| Codegen templates     | template digests        | Locked in `.eac/lock.json`                              |

## IR read/write window

| Role | Version |
| ---- | ------- |
| Write current | `0.2.0` |
| Prior stable (read) | `0.1.0` |
| Supported read set | `0.1.0`, `0.2.0` |

### IR 0.2.0 schema delta (from 0.1.0)

- **Additive:** `assurance_profile` (default `"baseline"`).
- **Normalized default:** `state_model_version` `"1"` → `"1.0"`.
- **Optional rename:** deprecated top-level `profile` → `assurance_profile` (then removed).

## Migration

`eac migrate` performs explicit IR upgrades to the compiler's current
`ir_version`. Transforms are applied in order (today: `0.1.0` → `0.2.0`).
Already-current documents are a documented identity/no-op. Unsupported
versions fail closed (`EAC3004`). Transform failures emit `EAC3006`.
Successful migrate status uses `EAC3005`.

Verification (`eac verify-pack`, lint, load) never silently migrates IR or packs.

## Release channels

- **alpha** — APIs may break without notice between minors.
- **beta** — IR and pack formats stabilize; breaking changes documented.
- **stable** — Full compatibility policy in force.
