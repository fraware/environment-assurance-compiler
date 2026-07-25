# Build an environment from traces

Operational traces are first-class sources with authority class
`operational_trace`. This guide uses `examples/refund/sources/trace-0187.jsonl`,
which shows a timed-out `submit_refund` that had already committed — contradicting
naive “always retry on 504” procedures.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## 1. Inspect the trace fixture

Inspect the JSONL fixture (one event per line):

```bash
# Unix
cat examples/refund/sources/trace-0187.jsonl
# Windows PowerShell
Get-Content examples/refund/sources/trace-0187.jsonl
```

Each line is a JSON event. The second event records `state_effect: committed`
after an earlier timeout; the third records a second commit (double refund).

## 2. Import traces into facts

```bash
eac init trace-ws --name trace-ws
eac import traces examples/refund/sources/trace-0187.jsonl \
  --path trace-ws \
  --output trace-ws/facts/trace_facts.json \
  --json
```

On success the facts file contains candidate claims about action outcomes,
timeouts, and state effects. Parse failures emit `EAC1004` and exit non-zero.

## 3. Reconcile against the OpenAPI contract

```bash
eac import openapi examples/refund/sources/api.yaml \
  --path trace-ws -o trace-ws/facts/api_facts.json

python - <<'PY'
from pathlib import Path
from envassure.facts.store import FactStore
from envassure.reconciliation import reconcile
from envassure.review import save_ambiguities

facts = []
for name in ("trace_facts.json", "api_facts.json"):
    facts.extend(FactStore.load(Path("trace-ws/facts") / name).list())
result = reconcile(facts)
save_ambiguities(Path("trace-ws/facts/ambiguities.json"), result.ambiguities)
print("open", [a.id for a in result.ambiguities if a.status == "open"])
for d in result.diagnostics.diagnostics:
    print(d.code, d.summary)
PY
```

## 4. Record an expert decision before packaging

Traces alone must not silently override contracts. Use `eac decide` (or the
review API) so the accepted interpretation is an `expert_decision`:

```bash
eac ambiguities --path .
# After reviewing open ids:
eac decide AMB-xxxx \
  --interpretation "Do not auto-retry after commit-unknown timeout" \
  --role domain_expert \
  --rationale "Trace shows double refund on naive retry" \
  --path .
```

## 5. Build, lint, and run a related world

The refund SDK world encodes the ambiguity demo:

```bash
eac build-ir --module examples/refund/world.py -o examples/refund/ir/world.json
eac lint examples/refund/ir/world.json --json
```

Until the ambiguity is closed, treat retry/idempotency diagnostics as expected
fail-closed signals — not as green lights to ship.

## Validation checklist

1. Trace import writes facts without `EAC1004`.
2. Reconciliation surfaces conflicts (`EAC2002`) or open ambiguities (`EAC2001`).
3. No release pack is built while required ambiguities remain open.
4. After decision, rebuild IR and re-run `eac lint` / `eac analyze`.
