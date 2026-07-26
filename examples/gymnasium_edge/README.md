# Gymnasium edge (E5)

Payload-bearing Gymnasium adapter demo (`spaces.Dict` actions + `check_env`).

## Requirements

```bash
pip install envassure[gym]
```

## Commands

```bash
./run.sh
./verify.sh
```

Both scripts require `eac` from an **installed wheel** on `PATH` (not only an
editable checkout).

## Status

Contract-complete for interface conformance. Not a production-fidelity or RL
trainer claim. PettingZoo remains experimental and is out of scope here.
