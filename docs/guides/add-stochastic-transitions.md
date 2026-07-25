# Add stochastic transitions

This guide uses `examples/inventory/` — a statistical inventory/scheduling world
with categorical fulfill/stockout branches.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## 1. Build and validate IR

```bash
eac build-ir --module examples/inventory/world.py -o examples/inventory/ir/world.json
eac lint examples/inventory/ir/world.json
eac analyze examples/inventory/ir/world.json --json
```

Key IR fields:

- `determinism: statistical`
- `stochasticity_model: categorical_branches`
- Transition `t_fulfill` with branches and probabilities summing to 1.0
- Hidden oracle `true_fill_rate` excluded from policy observations
- Resource counters declare `mutation_authority` and `resource_effects`

## 2. Confirm stochastic structure

```bash
python - <<'PY'
import importlib.util
from pathlib import Path
from envassure.analysis import analyze_world

root = Path("examples/inventory/world.py")
spec = importlib.util.spec_from_file_location("inv_world", root)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
world = mod.build_inventory_world()
assert world.determinism == "statistical"
stoch = [t for t in world.transitions if t.kind == "stochastic"]
assert stoch, "expected stochastic transitions"
for t in stoch:
    probs = [b.probability for b in t.branches if b.probability is not None]
    assert probs and abs(sum(probs) - 1.0) < 1e-6, (t.id, probs)
result = analyze_world(world)
assert not any(d.code == "EAC5002" for d in result.report.diagnostics)
print("stochastic ok", [t.id for t in stoch])
PY
```

Static analysis rejects probability sums ≠ 1.0 and missing branch probabilities
via `EAC4001`.

## 3. Differential probes for stochastic actions

```bash
eac differential examples/inventory/ir/world.json --max-probes 64 --json
```

The planner emits `stochastic.*` probes with a sample budget. Comparison uses
statistical conformance (`EAC7002`) when sample sizes are below the configured
minimum — binary equality is not treated as authoritative for stochastic worlds.

## 4. Package

```bash
eac package examples/inventory/ir/world.json -o inventory.eap
eac verify-pack inventory.eap
```

Declare `declared_fidelity_level` (here `EF-1`) and keep unsupported behavior in
`known_unsupported_behavior` when you extend the model.

## Checklist

1. Probabilities sum to 1.0 on every stochastic transition.
2. Policy observations omit evaluator-only state (`EAC5002` clean).
3. Resource writes include `resource_effects` (avoids `EAC4005` notes where required).
4. Termination/horizon fields align with `termination_semantics` (`EAC4007`).
5. Pack verifies.
