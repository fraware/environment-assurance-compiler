# Support / refund workflow (E1)

Public example contract for conflicting OpenAPI + SOP + trace sources around
`submit_refund` timeout / retry / idempotency.

Production reconcile emits a **stable hashed** ambiguity id; historical demo
label **AMB-0042** is a fixture alias in `world.py` only (never hard-coded in
the reconcile engine).

| Source | Path | Claim |
| ------ | ---- | ----- |
| API contract | `input/api.yaml` | `submit_refund` may return HTTP 504 with **no state semantics** |
| Approved SOP | `input/refund-sop.md` | Instructs agents to **retry** after timeout |
| Operational trace | `input/trace-0187.jsonl` | Timed-out attempt had already **committed**; retry double-applied |

Compatibility: the same files are also mirrored under `sources/` for older
guide paths.

## Example contract

```text
README.md
pyproject.toml
input/
expected/
run.sh
verify.sh
example-manifest.json
```

`run.sh` / `verify.sh` expect `eac` on `PATH` from an **installed wheel**
(not an editable checkout). From the repo root after `pip install dist/*.whl`:

```bash
./examples/refund/run.sh
./examples/refund/verify.sh
```

Manifest lint:

```bash
python scripts/lint_example_manifests.py
```

## Reconciliation demo

```bash
python -c "from examples.refund.world import reconcile_refund, find_amb_0042, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID; r=reconcile_refund(); a=find_amb_0042(r); print(a.id, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID); print(r.diagnostics.diagnostics)"
```

## Expected open ambiguity

Hashed id for `conflict|action:submit_refund|retry_behavior` (alias `AMB-0042`
in packaged demo docs). See `expected/ambiguity.json`. Release-grade packs must
record an expert decision via `eac decide` before projecting safe retry /
idempotency into IR.

## Build IR (open conflict)

Until the ambiguity is decided, expect retry/timeout diagnostics such as
`EAC4027`:

```bash
eac build-ir --module examples/refund/world.py -o examples/refund/ir/world.json
eac lint examples/refund/ir/world.json
```

Guide: [Build from OpenAPI](../../docs/guides/build-from-openapi.md).

## Author verification checklist

External authors should close the conflict, then build and verify a pack:

1. `eac init` a workspace and copy `input/` into its `sources/`
2. `eac import openapi|procedure|traces … --merge` for each source
3. `eac facts --reconcile` (expect a hashed open ambiguity for retry conflict)
4. `eac decide <ambiguity-id> -i … -r … --rationale …`
5. Project the decision into a workspace `world.py` (set `retry_behavior` /
   `idempotency`; mark the ambiguity `accepted`) — see
   `tests/fixtures/author/refund_decided_world.py`
6. `eac build-ir --path . --force`
7. `eac package ir/world.json -o pack.eap --profile authoring`
   (optional: `--fidelity ledger.json --sources-manifest sources.yml
   --workspace . --signature …`)
8. `eac verify-pack pack.eap`
9. Confirm `fidelity/ledger.json` is present with scoped claim entries
   (no aggregate fidelity score)

Automated coverage: `tests/test_refund_author_workflow.py`.
