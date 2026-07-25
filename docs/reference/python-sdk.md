# Python SDK

Public authoring surface (package `envassure`):

```python
from envassure import World, actor, state, action, task, __version__
```

## Minimal example

```python
from envassure import World

world = World(
    "demo.counter",
    "Counter",
    version="0.1.0",
    description="Deterministic counter",
)
world.state("count", type="scalar", initial=0)
world.actor("agent", available_actions=["increment", "reset"])
world.action("increment")
world.action("reset")
definition = world.definition  # WorldDefinition IR model
```

Decorators `state`, `action`, `actor`, and `task` mirror the fluent builders for
module-style authoring. Reference modules:

| Example | Module |
| ------- | ------ |
| Counter | `examples/counter/world.py` |
| Auth | `examples/auth/world.py` |
| Refund | `examples/refund/world.py` |
| Inventory | `examples/inventory/world.py` |

## Compile to IR

Export a `build_*_world()` function and compile with the CLI:

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
```

Or save programmatically via `envassure.ir` helpers used in tests and examples.

## Related

- [Environment IR](../concepts/environment-ir.md)
- [CLI `build-ir`](cli.md)
- [Schemas](schemas.md)
