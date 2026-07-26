# Environment IR

The **Environment Intermediate Representation** is a typed, versioned document
(`WorldDefinition`) that describes state, actors, observations, actions,
transitions, failures, tasks, verifiers, and evidence obligations — independent
of any RL framework
([ADR-0001](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0001-ir-independence-from-gymnasium.md)).

## Versioning

| Role | `ir_version` |
| ---- | ------------ |
| Write current | `0.2.0` |
| Prior stable (read) | `0.1.0` |

The compiler reads the last two stable minors and writes the current minor.
Upgrade with `eac migrate` only. See [Compatibility](../compatibility.md).

Notable `0.2.0` delta from `0.1.0`:

- additive `assurance_profile` (default `baseline`)
- normalized `state_model_version` (`"1"` → `"1.0"`)
- optional rename of deprecated top-level `profile` → `assurance_profile`

## Authoring

Prefer the manual Python SDK for reference packs:

```python
from envassure import World, state, action, actor, task

world = World("demo.counter", "Counter", version="0.1.0")
```

Compile:

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
```

JSON Schemas ship under
[`schemas/`](https://github.com/fraware/environment-assurance-compiler/tree/main/schemas)
(see also [Schemas reference](../reference/schemas.md)).

## Provenance

IR elements carry provenance links back to sources and decisions. Missing
provenance is treated as a release-grade defect. Use `eac explain` to walk an
element to its evidence.

`ProvenanceRef.origin_kind` classifies how the compiled element was obtained
(orthogonal to fact-layer `DerivationClass`):

| `origin_kind` | Meaning |
| ------------- | ------- |
| `source_derived` | Directly projected from source facts (`direct` / `observed`) |
| `inferred` | Compiler/adapter inference — must not be labeled `source_derived` |
| `default` | Compiler/SDK default with notes |
| `unresolved_conflict` | Open ambiguity awaiting a decision |
| `human_decision` | Expert decision record |
| `simulator_only` | Differential/simulator stub or known-unsupported behavior |
| `external_connector` | Live external dependency / connector |
| `fidelity_evidence` | Fidelity ledger evidence reference only |

Fact-layer `DerivationClass` remains the ingestion truth; IR `origin_kind` is
the compiled view. Validation rejects tagging inferred facts as
`source_derived` (`EAC3008`).

## Related concepts

- [Sources and facts](sources-and-facts.md)
- [Runtime and snapshots](runtime-and-snapshots.md)
- [Validation and fidelity](validation-and-fidelity.md)
