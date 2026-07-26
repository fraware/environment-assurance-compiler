# openenv_refund (E2)

OpenEnv export scaffold pinned to `openenv==0.4.1`.

## Requirements

```bash
pip install envassure[openenv]
```

## Commands

```bash
./run.sh    # eac openenv test + serve smoke (no full HTTP claim)
./verify.sh # pin + scaffold members
```

Use `eac` from an installed wheel. Full upstream OpenEnv HTTP serving remains
experimental; these scripts exercise the EnvAssure adapter path only.

## Status

Contract-complete for export/test/serve-smoke. Image coordinate after release:
`ghcr.io/fraware/envassure-openenv:<version>`.
