# Runtime and snapshots

The reference runtime is **event-sourced**
([ADR-0002](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0002-event-sourced-runtime.md)).

## Protocol

`AssuredEnvironment` supports:

- `reset` / `step`
- `state` / `observe`
- `snapshot` / `restore` / `fork`

Pipeline per step: validate actor/action → preconditions and authority →
deterministic or seeded outcome → emit events and side-effect intents → atomic
apply → observation / evidence / terminal status.

Strict mode forbids out-of-band mutation. Live external effects are **opt-in**;
the default records intents only.

## Determinism classes

Packs and worlds declare determinism, for example:

- fully deterministic
- seeded + recorded externals
- statistical
- externally nondeterministic

## CLI smoke path

```bash
eac run examples/counter/ir/world.json -a increment,increment --seed 0
eac snapshot examples/counter/ir/world.json -a increment -o snap.json
eac replay examples/counter/ir/world.json -a increment,increment
eac test examples/counter/ir/world.json
```

`--actions` / `-a` accepts comma-separated action ids or `actor:action` pairs.

## Framework adapters

Gymnasium and PettingZoo adapters live behind optional extras `[gym]` and
`[pettingzoo]` with lazy imports. Core IR and packaging never require them.
