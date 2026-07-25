# EnvAssure

**Package:** [`envassure`](https://github.com/fraware/environment-assurance-compiler)  
**CLI:** `eac`  
**License:** Apache-2.0  
**Status:** Pre-alpha (`0.1.0a0`)

Local-first **Environment Assurance Compiler**. It turns operational evidence
(API contracts, schemas, procedures, traces, expert decisions) into:

- a typed, versioned **Environment IR**
- an executable **event-sourced reference runtime**
- **assurance artifacts** (diagnostics, differential results, packs, reports)

EnvAssure helps you answer what state and actions exist, where evidence is
incomplete or conflicting, what the compiled model can actually run, and what
fidelity claims you can honestly make.

## What it is not

EnvAssure is **not** an RL trainer, model-serving platform, proof assistant, or
a single-number fidelity leaderboard. Building or packaging an environment does
**not** imply high fidelity — see [Validation and fidelity](docs/concepts/validation-and-fidelity.md)
and [ADR-0005](adrs/0005-fidelity-profile.md).

## Install

Requires Python 3.11 or 3.12.

```bash
pip install -e ".[dev]"
```

Optional extras (lazy-imported; fail closed when missing):

| Extra | Provides |
| ----- | -------- |
| `gym` | Gymnasium adapter |
| `pettingzoo` | PettingZoo adapter |
| `postgres` | Postgres DDL import + opt-in `PostgresReferenceConnector` |
| `model-assisted` | HTTP proposal provider (`httpx`); stub provider works without it |
| `docs` | MkDocs Material for local doc builds |

```bash
pip install -e ".[gym,pettingzoo,postgres,model-assisted,docs]"
```

## Quick start

```bash
eac --help
eac init my-env && cd my-env && eac doctor

# From the repository root — counter reference
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
eac run examples/counter/ir/world.json -a increment,increment
eac package examples/counter/ir/world.json -o counter.eap
eac verify-pack counter.eap
```

`eac run` accepts `--actions` / `-a` as comma-separated action ids (or
`actor:action` pairs). IR upgrades are explicit only:

```bash
eac migrate path/to/world.json -o path/to/world.migrated.json
```

Verification and lint never silently migrate IR.

## Documentation

| Area | Link |
| ---- | ---- |
| Docs home | [`docs/`](docs/) |
| Getting started | [`docs/getting-started.md`](docs/getting-started.md) |
| Compatibility | [`docs/compatibility.md`](docs/compatibility.md) |
| Threat model | [`docs/security/threat-model.md`](docs/security/threat-model.md) |
| ADRs | [`adrs/`](adrs/) |
| Examples | [`examples/`](examples/) |

Build the MkDocs site locally (optional):

```bash
pip install -e ".[docs]"
mkdocs build --strict
mkdocs serve
```

## Development

```bash
ruff check src tests
mypy src/envassure
pytest
```

CI runs on Python 3.11/3.12 (see [`.github/workflows/ci.yml`](.github/workflows/ci.yml)).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md).
Report vulnerabilities per [SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).
