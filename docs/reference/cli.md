# CLI reference

Entry point: **`eac`** (Typer).

## Global

| Flag | Meaning |
| ---- | ------- |
| `-h` / `--help` | Help |
| `-V` / `--version` | Package version |
| `--json` | Machine-readable diagnostics / results (most commands) |

Stable process codes: [exit codes](exit-codes.md).

## Workspace

| Command | Purpose |
| ------- | ------- |
| `eac init [PATH]` | Create workspace (`--name`, `--force`, `--json`) |
| `eac doctor` | Python, extras, config/lock checks (`--path`, `--network`, `--json`) |
| `eac inspect [PATH]` | Summarize workspace or IR document |

## IR and authoring

| Command | Purpose |
| ------- | ------- |
| `eac build-ir` | Compile manual SDK module (`--module`/`-m`, `--output`/`-o`, `--force`) |
| `eac lint` | Reference integrity (`--force` bypasses digest skip) |
| `eac generate` | Export schemas / generated runtime stubs |
| `eac migrate` | Explicit IR upgrade to write-current (`-o`, `--dry-run`) |
| `eac diff` | Classify semantic differences between two IR documents |
| `eac explain` | Trace an IR element via provenance |

## Import and reconciliation

| Command | Purpose |
| ------- | ------- |
| `eac import` | Import `openapi` / `database` / `policy` / `procedure` / `traces` |
| `eac facts` | List facts; `--reconcile` writes ambiguities |
| `eac ambiguities` | List ambiguity records |
| `eac decide` | Record an expert decision |

## Runtime and analysis

| Command | Purpose |
| ------- | ------- |
| `eac run` | Execute actions on `EventSourcedEnvironment` |
| `eac snapshot` | Run actions then write a restoreable snapshot |
| `eac replay` | Replay and verify deterministic digests |
| `eac test` | Reset + identical sequence → identical digests |
| `eac analyze` | Static assurance analyses |
| `eac coverage` | Multi-dimensional coverage |
| `eac differential` | Offline differential probes vs reference connectors |
| `eac refine` | CEGR intake into refinement generations |

### `eac run` actions

```bash
eac run path/to/world.json --actions increment,increment
eac run path/to/world.json -a actor:submit,approver:approve --seed 0
```

`--actions` / `-a` is a comma-separated list of bare action ids or `actor:action`
pairs.

### `eac migrate`

```bash
eac migrate path/to/world.json -o path/to/world.migrated.json
eac migrate path/to/world.json --dry-run
```

Never runs implicitly during `verify-pack`, lint, or load.

## Packs, reports, plugins, research

| Command | Purpose |
| ------- | ------- |
| `eac package` | Build `.eap` (`-o`, `--include-report` / `--no-include-report`) |
| `eac verify-pack` | Checksums + secret scan gates |
| `eac report` | Assurance-case JSON + HTML from canonical artifacts |
| `eac plugins` | `list` / `create` / `test` / `package` / `doctor` |
| `eac benchmark` | Offline fixture-oracle harness |

## Differential connector flags (summary)

Prefer `--fixture` or `--simulator` in CI. `--subprocess` requires
`--allow-subprocess`. `--http-url` requires `--allow-network` (loopback only).
See [Differentially validate](../guides/differentially-validate.md).
