# Release process

**Audience:** maintainers cutting EnvAssure package, container, and docs
releases.  
**Package name on PyPI / TestPyPI:** `envassure`  
**Repository:** [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)

This runbook is fail-closed: missing Environments, unsigned tags, or version
mismatches must stop the release. Do **not** publish with long-lived PyPI
tokens; use OIDC trusted publishing only.

## Version train

| Stage | Package version | Git tag | PyPI classifier |
| ----- | --------------- | ------- | --------------- |
| Development on `main` | `0.2.0.devN` | none | `Development Status :: 2 - Pre-Alpha` |
| Public beta cut | `0.2.0b1` | `v0.2.0b1` (annotated + signed) | `Development Status :: 4 - Beta` |
| Later betas / RC / stable | per SemVer | matching `v*` | update classifier at that cut |

Working tree version lives in
[`src/envassure/__init__.py`](https://github.com/fraware/environment-assurance-compiler/blob/main/src/envassure/__init__.py)
(Hatch reads it). Before tagging `v0.2.0b1`:

1. Set `__version__ = "0.2.0b1"`.
2. Set classifier to `Development Status :: 4 - Beta` in `pyproject.toml`.
3. Run `python scripts/check_tag_version.py` (also enforced in `release.yml`).

Do **not** set the Beta classifier on `0.2.0.dev*` builds — that would mislabel
development wheels. Keep Pre-Alpha until the `b1` tag commit.

## PyPI / TestPyPI name claim (manual — do this first)

The project name **`envassure` does not exist yet** on PyPI or TestPyPI.
**Do not** attempt first-time registration from CI. Complete the claim by hand,
then wire trusted publishing.

### 1. Claim on TestPyPI

1. Create / sign in at [https://test.pypi.org](https://test.pypi.org/).
2. Build a **local** throwaway wheel from a clean checkout (optional but
   recommended):

   ```bash
   python -m pip install --upgrade build twine
   python -m build
   ```

3. Upload once with an API token scoped to the new project (TestPyPI → Account
   settings → API tokens). Prefer a project-scoped token after the project
   exists; for the first upload a user token is required:

   ```bash
   twine upload --repository testpypi dist/*
   ```

4. Confirm [https://test.pypi.org/project/envassure/](https://test.pypi.org/project/envassure/)
   shows the project and that your account is Owner.

5. **Revoke** any user-scoped token used for the claim. Trusted publishing
   replaces tokens for CI.

### 2. Claim on PyPI

Repeat the same steps on [https://pypi.org](https://pypi.org/) so the name is
reserved under the same maintainer account(s). You may upload a matching
`0.2.0.dev0` (or wait and let the first real `0.2.0b1` be the first PyPI
artifact after trusted publishing is configured). Prefer claiming early with a
dev version so squatters cannot take the name.

Record Owners / Maintainers to match
[`MAINTAINERS.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/MAINTAINERS.md).

### 3. Configure trusted publishing (OIDC)

On **both** TestPyPI and PyPI, for project `envassure`:

1. Publishing → **Trusted publishers** → Add a new publisher.
2. Owner: `fraware`
3. Repository: `environment-assurance-compiler`
4. Workflow name: `release.yml`
5. Environment name:
   - TestPyPI publisher → `testpypi`
   - PyPI publisher → `pypi`
6. Save. Do **not** store `__token__` secrets in GitHub for routine publishes.

Until trusted publishing is saved, the Release workflow’s publish jobs must
fail closed (placeholders / environment protection without credentials).

## GitHub Environments (org / repo settings)

Create these Environments under **Settings → Environments**. Approval gates
are mandatory where noted.

| Environment | Purpose | Protection |
| ----------- | ------- | ---------- |
| `testpypi` | Upload to TestPyPI via OIDC | Optional reviewers; restrict to `release.yml` |
| `pypi` | Upload to PyPI via OIDC | **Required reviewers** (maintainer); no self-approve for stable if policy requires a second person |
| `github-pages` | Docs deploy artifact / Pages | Required reviewers for **stable** docs aliases; beta may be auto |
| `ghcr` | Push / retag GHCR images | **Required reviewers** for stable image aliases (`0.2`, non-beta); beta tags may use softer rules |

Also set Environment deployment branches / tags to `main` and `v*` as
appropriate. Never attach long-lived PyPI passwords to these Environments.

## Tag ruleset checklist (repository rules)

Create a repository ruleset (or branch/tag protection) with **all** of:

- [ ] Target tags matching `v*`
- [ ] Prevent force pushes to matching tags
- [ ] Prevent tag deletion
- [ ] Require tags to be **annotated** (not lightweight)
- [ ] Require tags to be **signed** (GPG or SSH signing) by an approved
      maintainer key listed in MAINTAINERS / org allowed signers
- [ ] Restrict who can create `v*` tags to maintainers
- [ ] Release commit must be reachable from `main` (no orphan tag tips);
      `release.yml` re-checks this and fails closed
- [ ] Status checks / rulesets on `main` remain required for merges

Local verification before tagging:

```bash
git fetch origin main
git merge-base --is-ancestor HEAD origin/main   # tag tip on main history
git tag -a -s v0.2.0b1 -m "envassure 0.2.0b1"
git verify-tag v0.2.0b1
python scripts/check_tag_version.py --tag v0.2.0b1
git push origin v0.2.0b1
```

## Release pipeline overview

Workflow: [`.github/workflows/release.yml`](https://github.com/fraware/environment-assurance-compiler/blob/main/.github/workflows/release.yml)

On `v*` tags (and dry-run `workflow_dispatch`):

1. Verify annotated + signed tag; checkout exact tag SHA.
2. `scripts/check_tag_version.py` — tag ↔ `__version__` must match.
3. Full gates (lint/type/tests subset as configured) + `python -m build`.
4. Fresh-venv wheel install; `eac --version` / `eac doctor` / one example smoke.
5. `SHA-256SUMS`, CycloneDX SBOM, `release-manifest.json`.
6. Publish to TestPyPI (`testpypi` Environment).
7. Publish to PyPI (`pypi` Environment, approval).
8. Attestations; attach identical assets to the GitHub Release.
9. Multi-arch GHCR build/push/sign (`ghcr` Environment); image scan.

Supporting workflows:

| Workflow | Role |
| -------- | ---- |
| `test-release.yml` | PR/main dry-run build + install + smoke (no publish) |
| `docs.yml` | Strict MkDocs build; Pages deploy on configured refs |
| `integrations.yml` | Matrix scaffold for reference integrations |
| `reproduce.yml` | Repro bundle scaffold + verify-without-checkout job |
| `security.yml` | Gitleaks, pip-audit, CodeQL, image scan |

## Container coordinates

- Image: `ghcr.io/fraware/envassure:<version>`
- Also: `0.2`, `beta`, `sha-<short>` on beta cuts
- **No** `latest` tag on beta
- Cosign keyless sign + SBOM attach; vuln scan fails on unresolved critical

Base image must be digest-pinned for publish paths (see `Dockerfile` and
`docker/base-image.lock`).

## Classifier note for `0.2.0b1`

Only on the commit tagged `v0.2.0b1`, set:

```toml
"Development Status :: 4 - Beta",
```

Dev builds stay on Pre-Alpha so TestPyPI/dev wheels are not labeled Beta.

## Docs aliases (mike)

Versioned publish paths for the beta cut (Material `extra.version.provider: mike`):

| Alias | Beta cut | Stable cut |
| ----- | -------- | ---------- |
| `/0.2.0b1/` | yes | historical |
| `/0.2/` | yes | yes (updates) |
| `/beta/` | yes | optional |
| `/stable/` | reserved | yes |

Deploy with `mike deploy` from the docs workflow; do **not** move `/stable/` on
a beta cut. Local contributors: `pip install -e ".[docs]"` then
`mkdocs build --strict`.

## Example contract gate

Before tagging, lint public example manifests:

```bash
python scripts/lint_example_manifests.py
```

E1 (`examples/refund/`) must be contract-complete. E2–E5 may remain scaffolds
until Milestone C qualifies integrations. `run.sh` / `verify.sh` must target an
installed wheel `eac` on `PATH`.

## Related

- [`MAINTAINERS.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/MAINTAINERS.md)
- [`CONTRIBUTING.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/CONTRIBUTING.md)
- [Development](development.md)
- [Governance](../governance/index.md)
- [Supply chain](../security/supply-chain.md)
- [Package and publish (Environment Packs)](../guides/package-and-publish.md)
- [Release notes](../release-notes.md)
- [Release readiness 0.2](../research/release-readiness-0.2.md)
