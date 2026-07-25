# Reference projects

| Example | Focus | Description |
| ------- | ----- | ----------- |
| [`counter/`](counter/) | Deterministic runtime | Manual SDK counter; pack + differential fixtures |
| [`auth/`](auth/) | Authorization / observability | Multi-actor approve/deny with hidden oracle |
| [`refund/`](refund/) | Conflicting sources | OpenAPI + SOP + trace ambiguity (expert decision) |
| [`inventory/`](inventory/) | Stochastic transitions | Categorical fulfill/stockout branches |

## Counter quick path

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
eac run examples/counter/ir/world.json -a increment,increment
eac package examples/counter/ir/world.json -o counter.eap
eac verify-pack counter.eap
```

Guides that use these projects live under [`docs/guides/`](../docs/guides/).
