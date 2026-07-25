# Support / refund workflow

Intentional conflicting sources for the classic `submit_refund` retry conflict.
Production reconcile emits a **stable hashed** ambiguity id; historical demo
label **AMB-0042** is a fixture alias in `world.py` only (never hard-coded in
the reconcile engine).

| Source | Path | Claim |
| ------ | ---- | ----- |
| API contract | `sources/api.yaml` | `submit_refund` may return HTTP 504 with **no state semantics** |
| Approved SOP | `sources/refund-sop.md` | Instructs agents to **retry** after timeout |
| Operational trace | `sources/trace-0187.jsonl` | Timed-out attempt had already **committed**; retry double-applied |

## Reconciliation demo

```bash
python -c "from examples.refund.world import reconcile_refund, find_amb_0042, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID; r=reconcile_refund(); a=find_amb_0042(r); print(a.id, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID); print(r.diagnostics.diagnostics)"
```

## Expected open ambiguity

Hashed id for `conflict|action:submit_refund|retry_behavior` (alias `AMB-0042`
in packaged demo docs). Release-grade packs must record an expert decision via
`eac decide` before projecting safe retry/idempotency into IR.

## Build IR

Until the ambiguity is decided, expect retry/timeout diagnostics such as
`EAC4027`:

```bash
eac build-ir --module examples/refund/world.py -o examples/refund/ir/world.json
eac lint examples/refund/ir/world.json
```

Guide: [Build from OpenAPI](../../docs/guides/build-from-openapi.md).
