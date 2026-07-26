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
Adapters **encode** IR-native observations at the boundary so Gymnasium spaces
match returned samples (enum labels → `Discrete` indices; numeric scalars →
`Box`; non-numeric / uninitialized scalars → `Text`). Core `observe()` remains
string-native. Release tests cover Gymnasium on `examples/counter` and
PettingZoo on `examples/auth` (term/trunc, `observation_space.contains`, legal
actions, `reason_code`).

Snapshots persist `initial_state_at_reset`. `restore` fail-closes unless
folding the event log onto that baseline reproduces `authoritative_state` and
`digests["state"]`. CLI `eac replay` exits non-zero on divergence or event-log
validation failures (`EAC9007`).

## Prior-defect regressions

These permanent regressions pin audit concerns that must not regress. Keep them
green across substrate work packages.

| Audit concern | Regression test(s) |
|---|---|
| Successful transitions mutate only by reconstructing committed events | `test_state_equals_fold_of_committed_events` |
| Restore requires reconstruct == authoritative state (+ state digest) | `test_restore_enforces_reconstruct_digest_equality` |
| Side-effect intent identifiers must be unique and idempotent (digest formula) | `test_intent_id_idempotent_for_same_inputs`, `test_intent_id_distinct_for_effect_or_transition_index`, `test_intent_ids_unique_within_multi_effect_run` |
| Snapshots must retain terminal / truncated episode state | `test_snapshot_v2_terminality_and_digests`, `test_terminal_outcome_when_episode_ended` |

## Run identity and deterministic intents

- `run_id` is the episode id set at `reset`. Pass `options={"episode_id": ...}`
  for cross-process stability; otherwise the runtime derives a seed-stable id
  (`ep-seed-{seed}`), never a per-step UUID.
- `transaction_id` is deterministic from `(run_id, transition_index)`.
- Side-effect `intent_id` values are `sei-{digest[:32]}` over
  `(run_id, transition_index, actor_id, action_id, effect_index,
  canonical_effect_payload_digest)`.
