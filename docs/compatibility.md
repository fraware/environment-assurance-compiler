# Compatibility Policy

EnvAssure versions several contracts independently:

| Contract              | Identifier              | Compatibility rule                                      |
| --------------------- | ----------------------- | ------------------------------------------------------- |
| Compiler package      | `envassure` PyPI ver.   | SemVer                                                  |
| IR schema             | `ir_version`            | Read last two stable minors; write current              |
| Plugin API            | `plugin_api_version`    | Breaking changes require major bump                     |
| Environment Pack      | pack `format_version`   | Write current; verify only supported read window |
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
- **Additive:** `ProvenanceRef.origin_kind` classifier for compiled IR provenance.

## Pack format read/write window

| Role | Version |
| ---- | ------- |
| Write current | `2` |
| Prior stable schema (frozen docs) | `1` (`pack-manifest-1.json`) |
| Supported pack read set | `2` |

Pack format **v2** requires `schemas/`, `sources/manifest.json`,
`provenance/bundle.json`, `migration/history.json`, `compatibility.json`,
`fidelity/ledger.json`, plus manifest fields `runtime_version` /
`policy_version`. Optional `signatures/` members must appear in
`manifest.files` when present, and `manifest.metadata.signatures` must list
matching per-member digests bound to a `signed_content_digest` over
non-signature members (integrity listing; not cryptographic verification).
Unsupported `format_version` values fail closed (`EAC8006`).

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

## Deprecation policy

1. **Announce** — Document the deprecation in this file and in the repository
   [CHANGELOG.md](https://github.com/fraware/environment-assurance-compiler/blob/main/CHANGELOG.md)
   under *Deprecated* for the release that introduces the warning or dual-read
   path.
2. **Dual support window** — Keep the old path readable for at least the
   **last two stable IR minors** (or one package minor on alpha) unless a
   security issue forces earlier removal.
3. **Migrate path** — Prefer explicit `eac migrate` / documented transforms over
   silent rewrite on lint, load, or `verify-pack`.
4. **Remove** — Removal is a breaking change: bump the relevant contract
   identifier (package major when stable; IR minor with migrate; plugin API
   major for plugin breaks) and list removals under *Removed* in the changelog.
5. **Diagnostics** — Prefer stable `EAC####` codes when emitting deprecation
   warnings so automation can gate on them.

Current deprecations:

| Surface | Status | Replacement |
| ------- | ------ | ----------- |
| Top-level IR field `profile` | Removed after rename in IR 0.2.0 migrate | `assurance_profile` |

## Release cadence

See the *Release cadence* note in
[CHANGELOG.md](https://github.com/fraware/environment-assurance-compiler/blob/main/CHANGELOG.md).
Pre-alpha (`0.1.0a0` → `0.2.0rc`) prioritizes remediation milestones over
calendar trains; after the first stable channel, expect documented minor trains
with changelog-gated deprecations as above.
