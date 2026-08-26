# Support / refund workflow (E1)

E1 is a public OpenAPI-backed environment example for conflicting API-contract,
approved-procedure, and operational-trace evidence around `submit_refund`
timeout/retry/idempotency semantics.

Production reconciliation emits a stable hashed ambiguity id. Historical label
`AMB-0042` is only a fixture alias for the classic retry conflict; the
reconciliation engine does not hard-code it.

| Source | Path | Evidence supplied |
| ------ | ---- | ----------------- |
| API contract | `input/api.yaml` | `submit_refund` endpoint, request/response shape, HTTP 504 with no authoritative state semantics |
| Approved SOP | `input/refund-sop.md` | instructs agents to retry after timeout |
| Operational trace | `input/trace-0187.jsonl` | one timed-out attempt had already committed; retry double-applied |

## Safety property demonstrated by the example

The raw sources are intentionally inconsistent. Before a decision, reconciliation
must emit `EAC4027`, persist the ambiguity record, and exit nonzero. The example
does **not** weaken that gate or compile the unresolved retry semantics.

`run.sh` then records an explicit `example_author` modeling decision:

```text
timeout_then_retry_requires_idempotency_key
```

Only after that decision is persisted does it copy `decided_world.py` into the
disposable workspace and compile `refund.v1`. The template refuses to build if
the accepted ambiguity or its decision artifact is missing.

The decided model contains:

- explicit `refund_status` state with OpenAPI provenance;
- a typed `support_agent`, observation projection, `submit_refund` action, and
  transition;
- action provenance linking OpenAPI + SOP + trace evidence and the persisted
  decision id;
- explicit retry behavior and `idempotency_key_required`;
- declared fidelity `EF-0`;
- a retained unsupported behavior: `live_payment_rail`.

Any other reconciliation ambiguity records remain visible. One decision is not
used to silently mark unrelated records resolved.

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
4. run `eac facts --reconcile`, **require its pre-decision failure**, and require
   `EAC4027` plus the classic open ambiguity;
5. record the explicit example-author decision with `eac decide`;
6. compile typed IR with `eac build-ir`;
7. lint with the `executable` profile;
8. execute one `agent:submit_refund` action and require the modeled state to become
   `committed`;
9. package `refund-authoring.eap` with the `authoring` profile;
10. verify the `.eap` with `eac verify-pack`.

`verify.sh` independently re-runs pack verification and checks the imported input
bytes, pre-decision failure evidence, persisted decision, executable lint result,
runtime result, IR and pack provenance, ambiguity statuses, source-manifest
disclosure, and fidelity ledger.

## Claim boundary

A clean `eac verify-pack` result establishes only that the `.eap` is structurally
well formed and its required members/checksums pass verification. It does **not**
establish high fidelity, empirical validation, production parity, or correctness
of the external payment rail.

The example remains `EF-0`. Its automatically seeded fidelity claim is only
`structurally_valid`, with `live_payment_rail` retained in `known_gaps`. The
`example_author` decision is a transparent modeling decision for this executable
example; it is not represented as independent domain-expert validation.

The example also deliberately packages without a workspace source manifest. The
pack therefore records its semantic source ids with `digest: null` and explicitly
states that no `sources.yml` was supplied. No acquisition metadata or source
digest is invented.

The authoring-profile pack is used because successful executable behavior does
not by itself satisfy research-release or deployment-calibration evidence
obligations.

## Reconciliation-only inspection

For a quick view of the undecided source conflict without running the complete
workflow:

```bash
python -c "from examples.refund.world import reconcile_refund, find_amb_0042, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID; r=reconcile_refund(); a=find_amb_0042(r); print(a.id, AMB_0042_ALIAS, CLASSIC_REFUND_RETRY_AMBIGUITY_ID); print(r.diagnostics.diagnostics)"
```

The expected classic conflict is documented in `expected/ambiguity.json`.

## Independent author path

The same evidence→decision→IR pattern is covered by
`tests/test_refund_author_workflow.py`. The fresh-wheel `Test release` workflow
also executes this public E1 `run.sh` / `verify.sh` contract on every PR and
`main`.

Manifest lint:

```bash
python scripts/lint_example_manifests.py
```

Guide: [Build from OpenAPI](../../docs/guides/build-from-openapi.md).
