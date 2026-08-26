# Support / refund workflow (E1)

E1 is a public OpenAPI-backed environment example for incomplete and conflicting
evidence around `submit_refund` timeout/retry/idempotency semantics.

Production reconciliation emits stable hashed ambiguity ids. Historical label
`AMB-0042` is only a fixture alias for the classic retry-policy conflict; the
reconciliation engine does not hard-code it.

| Source | Path | Evidence supplied |
| ------ | ---- | ----------------- |
| API contract | `input/api.yaml` | `submit_refund` endpoint, request/response shape, HTTP 504 with no authoritative state semantics |
| Approved SOP | `input/refund-sop.md` | instructs agents to retry after timeout |
| Operational trace | `input/trace-0187.jsonl` | one timed-out attempt had already committed; a later retry double-applied |

## Evidence ontology and safety property

EnvAssure distinguishes evidence observations from canonical action semantics:

- each JSONL event becomes a distinct `trace_event` with `observed_action`,
  `observed_outcome`, and optional `observed_timeout` /
  `observed_state_effect` facts;
- heterogeneous outcomes such as `timeout`, `observed_later`, and `ok` are
  therefore repeated observations, not contradictory definitions of
  `submit_refund`;
- an SOP merely mentioning timeout handling is recorded as
  `procedure_timeout_acknowledgement`, not as an alternative canonical
  `timeout_behavior`;
- only evidence that supports an operational-policy inference is projected onto
  a canonical predicate, and those heuristics retain
  `derivation_class=inferred`.

The real conflict is narrower: the SOP instructs `retry_on_timeout`, while the
trace supports the safety inference `do_not_retry_without_idempotency_key` after
a commit is observed following a timeout. Reconciliation must keep that retry
policy conflict open, emit `EAC4027`, and exit nonzero. E1 does **not** choose a
winner merely to make an executable demo.

`scoped_world.py` compiles only the supported non-timeout subset. It requires
exactly the classic retry conflict to remain open and omits executable
`timeout_behavior`, `retry_behavior`, and `idempotency` fields. Timeout
authoritative-state semantics remain incomplete even though the OpenAPI adapter
can extract the 504/no-state-semantics hint. Those fields and the external
payment rail are explicitly outside the runtime claim.

The scoped model contains:

- explicit `refund_status` state with OpenAPI provenance;
- a typed `support_agent`, observation projection, `submit_refund` action, and
  transition;
- action provenance linking OpenAPI + SOP + trace evidence, classified as
  `inferred` because the executable projection is narrower than the evidence;
- declared fidelity `EF-0`;
- known unsupported behavior `live_payment_rail`;
- known unsupported behavior `timeout_retry_idempotency_semantics`;
- the classic retry-policy ambiguity preserved as open, with no decision id.

The runtime sequence exercises only the modeled non-timeout action. It is not
evidence about timeout, retry, idempotency, or the external payment rail.

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
4. run `eac facts --reconcile`, require its expected nonzero exit and `EAC4027`,
   and require exactly the classic retry-policy semantic conflict;
5. copy `scoped_world.py`, which refuses to build if that conflict is missing,
   resolved, or accompanied by a spurious action-level semantic conflict;
6. compile typed IR with `eac build-ir`;
7. lint the scoped IR with the `executable` profile;
8. execute one non-timeout `agent:submit_refund` action and require modeled state
   to become `committed`;
9. package `refund-authoring.eap` with the `authoring` profile;
10. verify the `.eap` with `eac verify-pack`.

`verify.sh` independently audits the imported fact store as well as downstream
artifacts. It checks event-level observation cardinality, derivation classes,
canonical timeout/retry fact provenance, expected reconciliation failure,
absence of spurious timeout/outcome conflicts, absence of decision artifacts,
executable lint/runtime results, unsupported-semantics declarations, IR/pack
provenance, source-manifest disclosure, and the fidelity ledger.

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
used as evidence that the public scoped E1 conflict was resolved. The fresh-wheel
`Test release` workflow executes this public `run.sh` / `verify.sh` contract on
every PR and `main`.

Manifest lint:

```bash
python scripts/lint_example_manifests.py
```

Guide: [Build from OpenAPI](../../docs/guides/build-from-openapi.md).
