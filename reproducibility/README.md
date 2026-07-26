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
`expected-digests.json`. It does **not** require the EnvAssure source tree.

## Reproduce with checkout

From a full clone:

```bash
bash reproducibility/reproduce.sh
```

This re-verifies `packs/` via `eac pack verify`, refreshes digests, then runs
`verify.sh`.

## Related

- Benchmark packs: `packs/envassure-*`
- CLI: `eac pack lint|verify|reproduce|inspect`
- Concealed fixtures: `benchmarks/fixtures/`
