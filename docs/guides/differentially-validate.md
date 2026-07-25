# Differentially validate a system

Differential validation compares a compiled environment against a reference
connector on typed dimensions (success, observation, state, failure,
authorization, retry, idempotency, latency).

**Network is off by default.** Prefer recorded fixtures in CI.

## Prerequisites

```bash
pip install -e ".[dev]"
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
```

## 1. Offline in-memory reference (default)

```bash
eac differential examples/counter/ir/world.json --max-probes 32 --json
```

Without `--reference` / `--fixture`, both sides use the in-memory connector with
synthetic defaults — useful for plumbing checks, not fidelity claims.

## 2. Recorded fixture connector (recommended for CI)

A fixture lives at `tests/fixtures/differential/counter_reference.json`:

```bash
eac differential examples/counter/ir/world.json \
  --fixture tests/fixtures/differential/counter_reference.json \
  --max-probes 32 \
  --minimize \
  --json
```

The fixture schema:

```json
{
  "connector_name": "counter_recorded",
  "records": [
    {
      "probe_id": "normal.increment",
      "action_id": "increment",
      "outcome": {
        "success": true,
        "observation": {"count": 1},
        "state": {"count": 1}
      }
    }
  ]
}
```

Lookup order: `probe_id:action_id` → `probe_id` → `action_id` → sequential cursor.

## 3. File-backed simulator (local reference, no network)

Prefer a state-machine simulator when you need stateful reference behavior
beyond canned records. Definition at
`tests/fixtures/differential/counter_simulator.json` (also under
`examples/counter/sim/`):

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac differential examples/counter/ir/world.json \
  --simulator tests/fixtures/differential/counter_simulator.json \
  --max-probes 128 \
  --json
```

On the inventory workflow the planner expands to **≥100 probes** when
`--max-probes` is at least 100 (boundary grids, stochastic seed/sample variants,
pairwise sequences).

Python API:

```python
from envassure.differential import FileBackedSimulatorConnector, plan_probes

sim = FileBackedSimulatorConnector(
    definition_path="tests/fixtures/differential/counter_simulator.json"
)
sim.reset(0)
out = sim.execute("normal.increment", "increment", {})
assert out.state["count"] == 1
```

## 4. Subprocess reference (offline, opt-in)

For a local process that speaks JSON on stdin/stdout (still **no network**):

```bash
eac differential examples/counter/ir/world.json \
  --subprocess "python tests/fixtures/differential/counter_subprocess_stub.py" \
  --allow-subprocess \
  --max-probes 16 \
  --json
```

Construction fails closed without `--allow-subprocess`.

## 5. Counterexample minimization with reduction steps

When mismatches occur, `--minimize` (default) runs delta-debugging and records
each accepted reduction (`subset` / `complement` / `drop_one`) under
`minimized.reduction_steps` in the JSON output (`EAC7003`).

Python API:

```python
from envassure.differential import minimize_counterexample

result = minimize_counterexample(
    ["a", "b", "c", "d"],
    lambda seq: "c" in seq,
)
assert result.reduction_steps
assert result.minimized
```

## 6. Plugging a real reference

Implement `ReferenceConnector`:

```python
from envassure.differential import ProbeOutcome, ReferenceConnector

class MyReference:
    def name(self) -> str:
        return "my_reference"

    def reset(self, seed: int | None = None) -> None:
        ...

    def execute(self, probe_id: str, action_id: str, payload: dict) -> ProbeOutcome:
        ...
```

Options:

| Connector | Network | Use |
| --- | --- | --- |
| `InMemoryReferenceConnector` | none | Unit tests, scripts map |
| `RecordedFixtureConnector` | none | CI replay of captured outcomes |
| `FileBackedSimulatorConnector` | none | Stateful local simulator (counter/refund) |
| `SubprocessReferenceConnector` | none | Local JSON stdin/stdout process (opt-in) |
| `LocalHttpStubConnector` | **opt-in** loopback only | Local stub servers |

HTTP example (must pass `allow_network=True`, loopback host only):

```bash
# Start your stub on 127.0.0.1, then:
eac differential examples/counter/ir/world.json \
  --http-url http://127.0.0.1:8765/probe \
  --allow-network \
  --json
```

Remote hosts are rejected. Without `--allow-network`, construction fails closed.

## 7. Typed comparison dimensions

```python
from envassure.differential import (
    ComparisonDimension,
    ComparisonTolerances,
    compare_outcomes,
)

result = compare_outcomes(
    reference_outcome,
    candidate_outcome,
    world=world,
    tolerances=ComparisonTolerances(latency_ms=25.0),
    dimensions=[ComparisonDimension.SUCCESS, ComparisonDimension.AUTHORIZATION],
)
```

Stochastic worlds should pass sample pairs into `stochastic_samples` so
statistical notes (`EAC7002`) replace brittle binary equality.

## Checklist

1. Prefer `--fixture` or `--simulator` over live systems in CI.
2. Never enable `--allow-network` unless targeting a controlled loopback stub.
3. Use `--allow-subprocess` only for trusted local scripts.
4. Inspect minimized CE + `reduction_steps` before changing IR.
5. Treat dimension mismatches (`EAC7001`) as fail-closed for release claims.
6. Aim for ≥100 probes on rich workflows (`--max-probes 128`).
