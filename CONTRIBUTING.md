# Contributing

Thanks for your interest in EnvAssure (`envassure` / `eac`).

Extended guides (development, adapters, packs, defects, release runbook) live
under [`docs/contributing/`](docs/contributing/) and are linked from
[`docs/contributing.md`](docs/contributing.md).

## Development setup

1. Use **Python 3.11, 3.12, or 3.13**.
2. From the repository root:

   ```bash
   pip install -e ".[dev]"
   ```

3. Run the local gates:

   ```bash
   ruff check src tests
   mypy src/envassure
   pytest --cov=envassure --cov-fail-under=75
   coverage report --rcfile=.coveragerc.cores
   coverage report --rcfile=.coveragerc.assurance
   coverage report --rcfile=.coveragerc.semantic
   eac --help
   ```

   Coverage floors and SBOM / attestation verify steps are documented in
   [`docs/security/supply-chain.md`](docs/security/supply-chain.md).

4. Optional docs build (includes **mike** for versioned deploys):

   ```bash
   pip install -e ".[docs]"
   mkdocs build --strict
   ```

5. Optional public-example contract lint:

   ```bash
   python scripts/lint_example_manifests.py
   ```

Baseline capture commands for the 0.2 track are listed in
[`docs/research/release-readiness-0.2.md`](docs/research/release-readiness-0.2.md)
(do not claim green without recording measured output).

## Contribution checklist

Before opening a pull request:

- [ ] Change is independently useful (no silent success for unfinished CLI commands).
- [ ] New or changed public diagnostics are registered in
      `envassure.diagnostics.catalog.DIAGNOSTIC_CATALOG` **and** listed in
      [`docs/reference/diagnostics.md`](docs/reference/diagnostics.md).
- [ ] Tests cover the new behavior (including fail-closed paths).
- [ ] Docs / examples paths and CLI flags match the implementation
      (`--actions`/`-a`, `eac migrate`, etc.).
- [ ] IR migrations are **explicit** (`eac migrate` only) — never silent on
      `verify-pack`, lint, or load.
- [ ] No secrets, packs (`.eap`), or local `.eac/` state are committed.
- [ ] Security-sensitive changes note trust-boundary impact (see
      [`docs/security/threat-model.md`](docs/security/threat-model.md)).

## Developer Certificate of Origin (DCO)

All contributions must be signed off under the
[Developer Certificate of Origin](https://developercertificate.org/) v1.1.
Each commit message must include:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Use `git commit -s` (or your forge’s “sign-off” option) so the trailer is
added automatically. Unsigned commits are rejected.

By signing off, you certify that you have the right to submit the work under
the project’s Apache-2.0 license (see [`LICENSE`](LICENSE)).

## Pull requests

- Prefer small, reviewable changes; **require review before merging to `main`**.
- **Security-critical paths** (workflows, authorization, snapshots, packaging,
  diagnostics catalog, supply-chain docs, Dockerfile, release scripts — see
  [`.github/CODEOWNERS`](.github/CODEOWNERS)) require **two** approving reviews
  from maintainers listed in [`MAINTAINERS.md`](MAINTAINERS.md).
- Unimplemented CLI surfaces must fail closed with a stable diagnostic and a
  non-zero exit code (never exit `0` as success).
- Public IR schema changes need a design note, examples, compatibility analysis,
  migration plan, and at least two environment use cases (see governance in the
  project spec §25.4).
- Releases follow
  [`docs/contributing/release-process.md`](docs/contributing/release-process.md)
  (signed annotated `v*` tags, GitHub Environments, trusted publishing).

## Code standards

- Typed public API; mypy strict on `src/envassure`.
- No network by default in compiler paths; network features are opt-in.
- Canonical JSON digests for lockable artifacts.
- Model proposals are never authoritative facts without an expert path.

## Security

Report vulnerabilities privately per [SECURITY.md](SECURITY.md). Do not open
public issues for undisclosed vulnerabilities.

## Community standards

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
