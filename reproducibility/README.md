# EnvAssure reproducibility bundle

Frozen evidence layout for independently verifying public-beta research artifacts
without trusting an editable checkout.

## Layout

```text
reproducibility/
  README.md
  CITATION.cff
  MANIFEST.json
  source-commit.txt
  release-manifest.json
  environment/
  locks/
  inputs/
  configs/
  scripts/
  results/
  expected-digests.json
  hardware-and-platform.json
  limitations.md
  verify.sh
  reproduce.sh
```

## Verify without checkout

1. Download the published `reproducibility-bundle` artifact (or release tarball).
2. Extract and run:

```bash
bash verify.sh
```

`verify.sh` checks every `MANIFEST.json` member digest and
`expected-digests.json`. It does **not** require the EnvAssure source tree and it
does not establish behavioral or scientific equivalence.

## Reproduce with checkout

From a full clone:

```bash
bash reproducibility/reproduce.sh
```

This re-verifies the repository packs, refreshes the frozen bundle digests, and
runs `verify.sh`.

## Cross-Python `.eap` study

The release gate in `.github/workflows/cross-python-reproducibility.yml` builds
the same canonical `.eap` independently on Python 3.11 and 3.12 with a fixed
`SOURCE_DATE_EPOCH`. It requires byte-identical archives and equivalent
manifest/member digests, provenance, verifier diagnostics, and seeded runtime
events. The only declared interpreter-dependent evidence field is the recorded
Python version itself.

The comparison implementation is `scripts/cross_python_reproducibility.py`.
See `docs/reproducibility.md` for the exact contract and claim boundary.

## Related

- Benchmark packs: `packs/envassure-*`
- CLI pack verification: `eac pack verify`
- Public semantic-regression fixtures: `benchmarks/fixtures/`
