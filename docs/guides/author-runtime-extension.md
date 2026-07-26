# Author a runtime extension

The reference runtime is `EventSourcedEnvironment` (`envassure.runtime`):
reset → step → observe → snapshot / restore / fork. Steps follow
validate → authorize → preconditions → stage → commit (fail-closed).

## What you can extend safely

| Edge | Module / entry | Notes |
| ---- | -------------- | ----- |
| External effects | `ExternalEffectExecutor` | Live mode requires an injected executor; default is record-only receipts |
| Observation projections | `envassure.runtime.observations` | Missing / unknown / denied → empty dict (never full state) |
| Authorization atoms | `envassure.runtime.authorization` | Unknown schemes → `INDETERMINATE`, never allow |
| Expressions / effects | `envassure.expressions`, `runtime.effects` | Unsupported forms raise; never silent `False` |
| Snapshots | `runtime.snapshot` | Digest / world binding checked on restore |
| Gym / PettingZoo | `runtime.adapters` + extras | Missing extras fail closed (`EAC9003`) |
| Codegen targets | plugin kind `codegen_target` | Digests locked in `.eac/lock.json` |

## Author checklist

1. Surface typed failures (`StepOutcome`, diagnostics) for unsupported
   semantics — do not invent success.
2. Keep network and subprocess opt-in; live external effects need an explicit
   executor.
3. Treat generated code and packs as untrusted until verified.
4. Document fidelity limits; do not claim behavioral parity the IR cannot
   support.
5. Prefer plugins / extras over forking `runtime/engine.py` for product
   features.

## Related

- [Runtime and snapshots](../concepts/runtime-and-snapshots.md)
- [Plugin API](../reference/plugin-api.md)
- [Threat model](../security/threat-model.md)
- [Expressions / auth / observations](../reference/python-sdk.md) (SDK surface)
