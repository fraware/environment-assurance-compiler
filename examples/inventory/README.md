# Stochastic inventory / scheduling

Minimal statistical environment with fulfill/stockout branches and a hidden
`true_fill_rate` evaluator oracle omitted from policy observations.

```bash
eac build-ir --module examples/inventory/world.py -o examples/inventory/ir/world.json
eac lint examples/inventory/ir/world.json
eac analyze examples/inventory/ir/world.json
eac package examples/inventory/ir/world.json -o inventory.eap
eac verify-pack inventory.eap
```

Guide: [Add stochastic transitions](../docs/guides/add-stochastic-transitions.md).
