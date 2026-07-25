# Counter reference

Deterministic counter world authored with the manual Python SDK.

## Build and exercise

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
eac run examples/counter/ir/world.json -a increment,increment
eac package examples/counter/ir/world.json -o counter.eap
eac verify-pack counter.eap
```

Differential fixtures:

- `tests/fixtures/differential/counter_reference.json`
- `tests/fixtures/differential/counter_simulator.json`
- `examples/counter/sim/counter_simulator.json`
