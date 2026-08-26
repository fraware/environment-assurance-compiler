# Support / refund workflow (E1)

E1 is a public OpenAPI-backed environment example for conflicting API-contract,
approved-procedure, and operational-trace evidence around `submit_refund`
timeout/retry/idempotency semantics.

Production reconciliation emits stable hashed ambiguity ids. Historical label
`AMB-0042` is only a fixture alias for the classic retry conflict; the
reconciliation engine does not hard-code it.

| Source | Path | Evidence supplied |
| ------ | ---- | ----------------- |
| API contract | `input/api.yaml` | `submit_refund` endpoint, request/response shape, HTTP 504 with no authoritative state semantics |
| Approved SOP | `input/refund-sop.md` | instructs agents to retry after timeout |
| Operational trace | `input/trace-0187.jsonl` | one timed-out attempt had already committed; retry double-applied |

## Safety property demonstrated by the example

The raw sources are intentionally inconsistent. Reconciliation must emit
`EAC4027`, persist the ambiguity records, and exit nonzero. E1 does **not** choose
a winner for those conflicted operational facts merely to make an executable
demo.

Instead, `scoped_world.py` compiles only the non-conflicted subset of the model.
It requires the classic retry conflict to remain open and omits the disputed
`timeout_behavior`, `retry_behavior`, and `idempotency` fields from executable IR.
Those fields, plus authoritative state after HTTP 504, are explicitly listed as
unsupported semantics.

The scoped model contains:

- explicit `refund_status` state with OpenAPI provenance;
- a typed `support_agent`, observation projection, `submit_refund` action, and
  transition;
- action provenance linking OpenAPI + SOP + trace evidence, classified as
  `inferred` because the executable projection is narrower than the conflicting
  operational evidence;
- declared fidelity `EF-0`;
- known unsupported behavior `live_payment_rail`;
- known unsupported behavior `timeout_retry_idempotency_semantics`;
- all source-conflict ambiguity records preserved as open, with no decision ids.

The runtime sequence exercises only the modeled non-timeout action. It must not be
read as evidence about timeout, retry, idempotency, or the external payment rail.

## Run the public contract

`run.sh` and `verify.sh` require `eac` on `PATH` from an installed wheel rather
than an editable checkout. Invoke them through `bash` so execution does not depend
on checkout file-mode preservation:

```bash
bash examples/refund/run.sh
bash examples/refund/verify.sh
```

`run.sh` performs this sequence in `.example-out/workspace`:

1. `eac init`;
2. copy the three public inputs into `sources/`;
3. `eac import` OpenAPI, procedure, and traces;
4. run `eac facts --reconcile`, require its expected nonzero exit, require
   `EAC4027`, and require the classic open ambiguity;
5. copy `scoped_world.py`, which refuses to build if the classic conflict was
   silently resolved;
6. compile typed IR with `eac build-ir`;
7. lint the scoped IR with the `executable` profile;
8. execute one non-timeout `agent:submit_refund` action and require modeled state
   to become `committed`;
9. package `refund-authoring.eap` with the `authoring` profile;
10. verify the `.eap` with `eac verify-pack`.

`verify.sh` independently re-runs pack verification and checks the imported input
bytes, expected reconciliation failure, complete open-conflict inventory,
absence of decision artifacts, executable lint result, runtime result, omitted
operational fields, unsupported-semantics declarations, IR and pack provenance,
source-manifest disclosure, and fidelity ledger.

## Claim boundary

A clean `eac verify-pack` result establishes only that the `.eap` is structurally
well formed and its required members/checksums pass verification. It does **not**
establish high fidelity, empirical validation, production parity, or correctness
of the external payment rail.

The example remains `EF-0`. Its automatically seeded fidelity claim is only
`structurally_valid`; both `live_payment_rail` and
`timeout_retry_idempotency_semantics` remain in `known_gaps`. There is no expert
reviewer and no decision artifact in the scoped public contract.

The example deliberately packages without a workspace source manifest. The pack
therefore records its semantic source ids with `digest: null` and explicitly
states that no `sources.yml` was supplied. No acquisition metadata or source
digest is invented.

The authoring-profile pack is used because successful execution of a deliberately
scoped path does not satisfy research-release or deployment-calibration evidence
obligations.

## Reconciliation-only inspection

For a quick view of the source conflict without running the complete workflow:

```bash
python -c "from examples.refund.world import reconcile_refund, find_amb_0042, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID; r=reconcile_refund(); a=find_amb_0042(r); print(a.id, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID); print(r.diagnostics.diagnostics)"
```

The expected classic conflict is documented in `expected/ambiguity.json`.

## Separate decision-path coverage

`tests/test_refund_author_workflow.py` covers a separate author workflow in which
an explicit decision is recorded and projected. That test is intentionally not
used as evidence that the public scoped E1 conflicts were resolved. The
fresh-wheel `Test release` workflow executes this public `run.sh` / `verify.sh`
contract on every PR and `main`.

Manifest lint:

```bash
python scripts/lint_example_manifests.py
```

Guide: [Build from OpenAPI](../../docs/guides/build-from-openapi.md).
