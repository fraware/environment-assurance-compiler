# Limitations

EnvAssure deliberately does **not** provide:

- an RL trainer or policy optimization loop
- a model-serving / agent hosting platform
- a general-purpose proof assistant
- a composite fidelity leaderboard or single-number pack ranking
- automatic trust for third-party packs or plugins
- silent repair of missing operational semantics

## Honest fidelity bounds

- OpenAPI / DDL / SOP import yields **facts**, not a finished high-fidelity world.
- In-memory differential connectors validate plumbing, not production parity.
- Statistical worlds need sample-aware comparison (`EAC7002`); binary equality is
  insufficient.
- Optional extras (`gym`, `pettingzoo`, `postgres`, `model-assisted`) are not
  required for core assurance workflows.

## Operational constraints

- Local-first: network features are opt-in (`eac doctor --network`, differential
  `--allow-network`, subprocess `--allow-subprocess`).
- IR migrate is explicit only (`eac migrate`).
- Pre-alpha (`0.1.0a0`): public APIs and IR minors may change within the
  [compatibility policy](../compatibility.md).

See [Validation and fidelity](../concepts/validation-and-fidelity.md).
