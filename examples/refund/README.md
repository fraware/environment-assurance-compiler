# Support / refund workflow (E1)

Public OpenAPI-backed environment example for conflicting API-contract, approved
procedure, and operational-trace evidence around `submit_refund` timeout / retry /
idempotency semantics.

Production reconciliation emits a **stable hashed** ambiguity id; historical demo
label **AMB-0042** is a fixture alias in `world.py` only (never hard-coded in the
reconciliation engine).

| Source | Path | Evidence supplied |
| ------ | ---- | ----------------- |
| API contract | `input/api.yaml` | `submit_refund` endpoint, request/response shape, HTTP 504 with **no authoritative state semantics** |
| Approved SOP | `input/refund-sop.md` | instructs agents to **retry** after timeout |
| Operational trace | `input/trace-0187.jsonl` | one timed-out attempt had already **committed**; retry double-applied |

Compatibility: the same files are also mirrored under `sources/` for older guide
paths.

## What the typed model contains

`world.py` projects the evidence into a typed `refund.v1` environment with:

- explicit `refund_status` state and source provenance;
- a typed `support_agent` actor and observation projection;
- a typed `submit_refund` action and transition;
- action provenance linking the OpenAPI, SOP, and trace sources;
- declared fidelity `EF-0`;
- one compound known gap: **authoritative state / retry / idempotency semantics
  after an HTTP 504 are unresolved until expert decision**.

The model deliberately leaves `retry_behavior` and `idempotency` unset and marks
`authoritative_state_on_504` unsupported. A successful non-timeout action can be
executed; the disputed timeout/retry path is not silently invented.

## Public example contract

```text
README.md
pyproject.toml
input/
expected/
run.sh
verify.sh
example-manifest.json
```

`run.sh` / `verify.sh` require `eac` on `PATH` from an **installed wheel** rather
than an editable checkout. Invoke them through `bash` so the documented path does
not depend on executable-bit preservation in a checkout. From the repository root
after `pip install dist/*.whl`:

```bash
bash examples/refund/run.sh
bash examples/refund/verify.sh
```

`run.sh` performs the following executable path:

1. imports/reconciles the real example sources and requires the classic conflict
   to remain open;
2. builds typed IR;
3. lints the IR;
4. runs one modeled, non-timeout `agent:submit_refund` action;
5. packages `refund-authoring.eap` with `--profile authoring`;
6. verifies the `.eap` with `eac verify-pack`.

Artifacts are written under `.example-out/`. `verify.sh` independently re-runs
pack verification and checks state/action provenance, the open ambiguity, the
runtime step, the embedded provenance bundle, source-manifest disclosure, and
the scoped fidelity ledger.

### Claim boundary

A clean `verify-pack` result means that the pack is structurally well formed and
its declared members/checksums pass verification. It **does not** mean the model
is high fidelity, empirically validated, or production-equivalent. This example
remains `EF-0`; the default fidelity claim is only `structurally_valid`, with the
known retry/idempotency gap retained. No source digest is invented when a
workspace `sources.yml` was not supplied.

The authoring-profile pack is intentionally suitable for demonstrating an
incomplete model. Resolve the ambiguity before making stronger release-profile
or fidelity claims.

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
in packaged demo docs). The OpenAPI response code cannot establish whether a
504 occurred before or after the authoritative refund commit. The procedure and
trace therefore conflict on safe retry semantics.

## Closing the ambiguity as an external author

To move beyond the intentionally incomplete authoring example:

1. `eac init` a workspace and copy `input/` into its `sources/`;
2. `eac import openapi|procedure|traces … --merge` for each source;
3. `eac facts --reconcile` and inspect the hashed retry conflict;
4. `eac decide <ambiguity-id> -i … -r … --rationale …`;
5. project the accepted decision into a workspace `world.py` (set
   `retry_behavior` / `idempotency`) — see
   `tests/fixtures/author/refund_decided_world.py`;
6. `eac build-ir --path . --force`;
7. lint and run only paths justified by the resulting semantics;
8. `eac package ir/world.json -o pack.eap --profile authoring` (or a stricter
   profile only when its obligations are actually met);
9. `eac verify-pack pack.eap`;
10. inspect `fidelity/ledger.json` as scoped claims, never an aggregate fidelity
    score.

Automated coverage for the decided author path lives in
`tests/test_refund_author_workflow.py`. The fresh-wheel release workflow also
executes this public E1 `run.sh` / `verify.sh` contract.

Guide: [Build from OpenAPI](../../docs/guides/build-from-openapi.md).
