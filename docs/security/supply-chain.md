# Supply chain — SBOM and release provenance

**Status:** Living document  
**Scope:** CI dependency audit, immutable automation dependencies, CycloneDX SBOM
generation, and GitHub build-provenance attestations for EnvAssure distributions  
**Repository:** [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)

## What CI enforces

| Check | Workflow / job | Policy |
| ----- | -------------- | ------ |
| Lint / type / pytest + coverage floors | `CI` → `lint-type-test` | **Blocking** |
| Multi-OS `eac` smoke | `CI` → `smoke` | **Blocking** |
| Optional extras import (`gym`, `pettingzoo`, `postgres`, `model-assisted`) | `CI` → `extras-import` | **Blocking** |
| Offline `eac benchmark` regression | `CI` → `benchmark` | **Blocking** |
| sdist / wheel + package acceptance (§4.4) | `CI` → `package` | **Blocking** |
| MkDocs strict | `CI` → `docs` / `Docs` | **Blocking** |
| Counter E2E + pack secret scan | `CI` → `counter-e2e` | **Blocking** |
| Schema / fixture JSON | `CI` → `schemas` | **Blocking** |
| Immutable remote workflow refs | `CI` → `schemas` (`check_workflow_action_pins.py`) | **Blocking** |
| Gitleaks | `Security` → `secret-scan` | **Blocking** |
| `pip-audit` on installed runtime deps | `Security` → `dependency-audit` | **Blocking** |
| CodeQL (same-repo only) | `Security` → `codeql` | **Blocking** |
| Trivy fs / image CRITICAL | `Security` → `image-scan` / `Release` → `ghcr` | **Blocking** |
| CycloneDX SBOM preview artifact | `CI` → `sbom-preview` | **Advisory** (`continue-on-error`) |
| Signed tag → build → TestPyPI/PyPI/GHCR | `Release` | **Blocking** on `v*` / dispatch |
| Dry-run build + acceptance | `Test release` | **Blocking** on PR/main |

### CI/CD dependency integrity

Remote GitHub Actions are referenced by exact 40-character commit SHA, with a
human-readable release/major comment next to each pin. A branch or tag such as
`@v4`, `@main`, or `@release/v1` is not accepted by the repository policy because
its target can move without changing this repository. Repository-local
`./...` actions and reusable workflows are tied to the checked-out revision.
Container actions, if introduced through `docker://`, must use an explicit
`@sha256:<digest>` image reference.

`scripts/check_workflow_action_pins.py` scans every YAML file under
`.github/workflows/` and fails blocking CI on a mutable or malformed remote
`uses:` reference. Its regression tests cover exact commit pins, mutable tags,
local actions, missing refs, and container digest rules.

`.github/dependabot.yml` checks the `github-actions` ecosystem weekly. Updating a
pin therefore requires an explicit repository change and normal review/CI rather
than inheriting an upstream tag mutation invisibly. Pinning is not a claim that an
upstream Action is intrinsically trustworthy; it makes the exact dependency
reviewable, reproducible, and auditable.

Direct executable downloads follow the same fail-closed principle. OPA and
Gitleaks are version-pinned and checked against repository-pinned SHA-256 digests
before execution; downloads use bounded connection/transfer time and retries.
Changing a version requires changing its expected digest in the same reviewed
repository history. A versioned URL by itself is not treated as an integrity
control.

Coverage floors (measured 2026-07-25, branch coverage):

| Gate | Threshold | Notes |
| ---- | --------- | ----- |
| Overall `--cov=envassure` | **75%** | Suite ~78%; floor leaves a small buffer |
| Cores (omit CLI / adapters / tasks) | **80%** | `.coveragerc.cores` (~83% measured) |
| Assurance packages (IR, packaging, workspace, diagnostics, facts, reports, `differential.compare`) | **80%** | `.coveragerc.assurance` (~85% measured) |
| Semantic cores (`expressions`, runtime auth/payloads/observations/engine/effects/external/snapshot, `differential.compare`, reconciliation) | **90%** | `.coveragerc.semantic` (~91% measured) |
| Security-critical branches | dedicated unit tests | Prefer fail-closed path tests over forcing 100% branch cov |

CI PR jobs cap concealed benchmarks at `--max-probes 20` for latency. Full
offline probe counts (≥100 curated + generated per workflow fixture) run via
`eac benchmark --concealed` locally or the schedule workflow
`.github/workflows/nightly-empirical.yml` (no secrets required).

## SBOM

Release builds (and the advisory CI preview) emit a CycloneDX document via
[`cyclonedx-bom`](https://github.com/CycloneDX/cyclonedx-python) against a clean
venv that installs the built wheel:

- `dist/envassure.cdx.json`
- `dist/envassure.cdx.xml`

On a published GitHub Release these files are attached as release assets
together with `SHA-256SUMS` and `release-manifest.json` (also uploaded as the
`envassure-release-dist` workflow artifact).

### Release manifest

`schemas/release-manifest-1.json` defines the compiler release coordinate
document. Generate with:

```bash
python scripts/generate_release_manifest.py \
  --dist-dir dist \
  --tag v0.2.0b1 \
  --commit "$(git rev-parse HEAD)" \
  --out dist/release-manifest.json
```

Maintainer Environments, PyPI name claim, and tag rulesets:
[release process](../contributing/release-process.md).

### Verify an SBOM locally

```bash
python -m pip install --upgrade build cyclonedx-bom
python -m build
python -m venv /tmp/eac-sbom && /tmp/eac-sbom/bin/pip install dist/*.whl cyclonedx-bom
/tmp/eac-sbom/bin/cyclonedx-py environment /tmp/eac-sbom/bin/python \
  -o envassure.cdx.json --of JSON --pyproject pyproject.toml --mc-type library
python -c "import json; d=json.load(open('envassure.cdx.json')); assert d['bomFormat']=='CycloneDX'; print(len(d.get('components') or []))"
```

Compare the release asset digest to your local rebuild when auditing a tag.

## Build provenance (attestations)

The `Release` workflow uses GitHub OIDC and
[`actions/attest-build-provenance`](https://github.com/actions/attest-build-provenance)
to attest wheels, sdists, and SBOM files. The Action itself is commit-pinned in
the workflow. Attestations are stored in the repository’s **Attestations** UI
(GitHub Artifact Attestations) and can be verified with the GitHub CLI without a
separate Sigstore key ceremony.

### Verify provenance

```bash
# After downloading a release wheel (example name):
gh attestation verify dist/envassure-*.whl --repo fraware/environment-assurance-compiler

# Same for SBOM:
gh attestation verify dist/envassure.cdx.json --repo fraware/environment-assurance-compiler
```

Expect a successful verification that cites the `Release` workflow identity.
If `gh attestation verify` is unavailable, upgrade the GitHub CLI or inspect
Attestations in the GitHub repository UI for the release commit.

### Triggering a release build

- Automatic: push a signed annotated `v*` tag (see release-process).
- Manual: Actions → **Release** → **Run workflow** (dry-run by default;
  optional TestPyPI / PyPI / GHCR publish flags).

## Related

- [Threat model](threat-model.md)
- [Release process](../contributing/release-process.md)
- [Package and publish](../guides/package-and-publish.md)
- [Release readiness 0.2](../research/release-readiness-0.2.md)
- [SECURITY.md](https://github.com/fraware/environment-assurance-compiler/blob/main/SECURITY.md)
