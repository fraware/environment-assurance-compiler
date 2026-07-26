# Authorization workflow reference

Multi-actor approve/deny with partial observability (`examples/auth/`).

```bash
eac build-ir --module examples/auth/world.py -o examples/auth/ir/world.json
eac lint examples/auth/ir/world.json
eac analyze examples/auth/ir/world.json
eac run examples/auth/ir/world.json -a requester:submit,approver:approve
```

Enum string effects use quoted literals (`request_status = "pending"`). Bare
names are treated as state paths and would leave status `None`.

Core `observe()` returns IR-native string enum labels. Gymnasium / PettingZoo
adapters encode those labels to `Discrete` indices so
`observation_space.contains(obs)` holds.

PettingZoo adapter release coverage uses this world
(`tests/test_adapters_release.py`, marker `pettingzoo`).

See the guide [Add authorization](../docs/guides/add-authorization.md).
