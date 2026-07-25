# Authorization workflow reference

Multi-actor approve/deny with partial observability (`examples/auth/`).

```bash
eac build-ir --module examples/auth/world.py -o examples/auth/ir/world.json
eac lint examples/auth/ir/world.json
eac analyze examples/auth/ir/world.json
eac run examples/auth/ir/world.json -a submit,approve
```

See the guide [Add authorization](../docs/guides/add-authorization.md).
