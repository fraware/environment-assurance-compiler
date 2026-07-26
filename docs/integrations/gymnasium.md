# Gymnasium

Status: **release-qualified** for the single-agent adapter (Milestone C1).

## Install

```bash
pip install envassure[gym]
```

| Surface | Notes |
| ------- | ----- |
| Extra | `gymnasium>=0.29` |
| Adapter | `GymAssureEnv` — real `gymnasium.Env` subclass |
| Registration | `register_gymnasium_envs()` → `EnvAssure/Generic-v0` |
| Rewards | `RewardProvider` in `envassure.runtime.rewards` (neutral + `reward_status="unconfigured"` by default) |
| PettingZoo | `[pettingzoo]` remains **experimental**; no conformance claim |

## Conformance

```bash
python -c "from gymnasium.utils.env_checker import check_env; ..."
pytest -m gym tests/test_adapters_release.py
```

Supported observation types: scalar, enum, resource_counter, timestamp, duration,
record, list (record/list use a lossy JSON-Text codec). Map/graph/opaque fail
closed without a codec plugin. Payload-bearing actions use `spaces.Dict`.

## What is not claimed

- Interface conformance ≠ production fidelity.
- RL trainer capabilities are out of scope.

## Related

- [Author a runtime extension](../guides/author-runtime-extension.md)
- [OpenEnv](openenv.md)
