# Supply chain — SBOM and release provenance

**Status:** Living document  
**Scope:** CI dependency audit, CycloneDX SBOM generation, and GitHub
build-provenance attestations for EnvAssure distributions  
**Repository:** [fraware/environment-assurance-compiler](https://github.com/fraware/environment-assurance-compiler)

## What CI enforces

| Check | Workflow / job | Policy |
| ----- | -------------- | ------ |
| Lint / type / pytest + coverage floors | `CI` → `lint-type-test` | **Blocking** |
| Multi-OS `eac` smoke | `CI` → `smoke` | **Blocking** |
| Optional extras import (`gym`, `pettingzoo`, `postgres`, `model-assisted`) | `CI` → `extras-import` | **Blocking** |
| Offline `eac benchmark` regression | `CI` → `benchmark` | **Blocking** |
| sdist / wheel clean install | `CI` → `package` | **Blocking** |
| MkDocs strict | `CI` → `docs` | **Blocking** |
| Counter E2E + pack secret scan | `CI` → `counter-e2e` | **Blocking** |
| Schema / fixture JSON | `CI` → `schemas` | **Blocking** |
| Gitleaks | `CI` → `secret-scan` | **Blocking** |
| `pip-audit` on installed runtime deps | `CI` → `dependency-audit` | **Blocking** |
| CodeQL (same-repo only) | `CI` → `codeql` | **Blocking** |
| CycloneDX SBOM preview artifact | `CI` → `sbom-preview` | **Advisory** (`continue-on-error`) |
| Signed build provenance + release SBOM | `Release` → `build-sbom-attest` | **Blocking** on release / dispatch |

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

On a published GitHub Release these files are attached as release assets (also
uploaded as the `envassure-dist-sbom` workflow artifact).

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
to attest wheels, sdists, and SBOM files. Attestations are stored in the
repository’s **Attestations** UI (GitHub Artifact Attestations) and can be
verified with the GitHub CLI without a separate Sigstore key ceremony.

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

- Automatic: publish a GitHub Release (tag).
- Manual: Actions → **Release** → **Run workflow** (optionally upload assets to
  the latest release).

## Related

- [Threat model](threat-model.md)
- [Package and publish](../guides/package-and-publish.md)
- [Release readiness 0.2](../research/release-readiness-0.2.md)
- [SECURITY.md](https://github.com/fraware/environment-assurance-compiler/blob/main/SECURITY.md)
