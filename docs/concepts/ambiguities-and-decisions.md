# Ambiguities and decisions

When sources conflict or omit critical semantics (timeouts, retries,
idempotency, authorization), EnvAssure records an **ambiguity** instead of
guessing.

## Lifecycle

1. Import sources → semantic facts.
2. Reconcile → open `AmbiguityRecord`s (`EAC2001` while open; conflicts as
   `EAC2002`).
3. Expert records a decision with `eac decide` (role, interpretation, rationale).
4. IR / packs may claim release grade only after required ambiguities are closed.

The refund example (`examples/refund/`) intentionally conflicts OpenAPI, SOP,
and trace evidence around HTTP 504 retry (demo id `AMB-0042` in packaged flows).

## Commands

```bash
eac facts --reconcile
eac ambiguities --path .
eac decide AMB-xxxx \
  --interpretation "Do not auto-retry after commit-unknown timeout" \
  --role domain_expert \
  --rationale "Trace shows double refund on naive retry"
```

Decisions on unknown or already-closed ambiguities fail closed (`EAC2004`).

## CEGR

Counterexample-guided reconciliation (`eac refine`) can open new ambiguities or
propose corrected facts / transition patches from differential failures
(`EAC7004` / `EAC7005`). Proposals still require expert disposition.
