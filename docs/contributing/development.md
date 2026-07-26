# Development

Local development for EnvAssure contributors. The root
[CONTRIBUTING.md](https://github.com/fraware/environment-assurance-compiler/blob/main/CONTRIBUTING.md)
remains the entry checklist; this page expands day-to-day workflows.

## Setup

1. Use Python **3.11**, **3.12**, or **3.13**.
2. From the repository root:

   ```bash
   pip install -e ".[dev]"
   ```

3. Optional documentation toolchain (includes **mike** for versioned deploys):

   ```bash
   pip install -e ".[docs]"
   mkdocs build --strict
   ```

## Local gates

```bash
ruff check src tests
mypy src/envassure
pytest --cov=envassure --cov-fail-under=75
coverage report --rcfile=.coveragerc.cores
coverage report --rcfile=.coveragerc.assurance
coverage report --rcfile=.coveragerc.semantic
eac --help
```

Coverage floors and supply-chain verification are documented in
[Supply chain](../security/supply-chain.md).

## Docs versioning (mike)

Versioned site aliases planned for the beta cut:

| Alias | Role |
| ----- | ---- |
| `/0.2.0b1/` | Exact beta tag |
| `/0.2/` | Minor train |
| `/beta/` | Moving beta pointer |
| `/stable/` | Reserved until a stable release |

Deploy uses `mike deploy` / `mike set-default` from release workflows (Milestone A),
not from ad-hoc local publishes to `gh-pages` without review.

Material's version selector is configured via `extra.version.provider: mike` in
`mkdocs.yml`.

## Public examples

Every public example should follow the contract:

```text
README.md
pyproject.toml   # or lock file
input/
expected/
run.sh
verify.sh
example-manifest.json
```

- `run.sh` / `verify.sh` must target an **installed wheel** `eac` on `PATH`
  (CI installs from `dist/`), not an editable checkout assumption.
- Lint manifests with:

  ```bash
  python scripts/lint_example_manifests.py
  ```

Reference: [`examples/refund/`](https://github.com/fraware/environment-assurance-compiler/tree/main/examples/refund) (E1).

## Related

- [Source adapters](source-adapters.md)
- [Runtime adapters](runtime-adapters.md)
- [Release process](release-process.md)
