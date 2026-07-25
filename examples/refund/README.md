# Support / refund workflow

Intentional conflicting sources for expert decision **AMB-0042**:

| Source | Path | Claim |
| ------ | ---- | ----- |
| API contract | `sources/api.yaml` | `submit_refund` may return HTTP 504 with **no state semantics** |
| Approved SOP | `sources/refund-sop.md` | Instructs agents to **retry** after timeout |
| Operational trace | `sources/trace-0187.jsonl` | Timed-out attempt had already **committed**; retry double-applied |

## Reconciliation demo

```bash
python -c "from examples.refund.world import reconcile_refund, find_amb_0042; r=reconcile_refund(); print(find_amb_0042(r).id); print(r.diagnostics.diagnostics)"
```

## Expected open ambiguity

`AMB-0042` — conflict on retry/timeout semantics for `submit_refund`.
Release-grade packs must record an expert decision via `eac decide` before
projecting safe retry/idempotency into IR.

## Build IR

Until the ambiguity is decided, expect retry/timeout diagnostics such as
`EAC4027`:

```bash
eac build-ir --module examples/refund/world.py -o examples/refund/ir/world.json
eac lint examples/refund/ir/world.json
```

Guide: [Build from OpenAPI](../docs/guides/build-from-openapi.md).
