# Build an environment from OpenAPI

This guide uses the refund example at `examples/refund/`. The OpenAPI contract
at `examples/refund/sources/api.yaml` is intentionally incomplete about HTTP 504
retry semantics — EnvAssure imports that incompleteness as facts rather than
inventing behavior.

## Prerequisites

```bash
pip install -e ".[dev]"
eac --version
```

Requires Python 3.11+.

## 1. Create a workspace (optional but recommended)

```bash
eac init refund-ws --name refund-ws
cd refund-ws
eac doctor
```

`eac doctor` checks the Python version and workspace layout. Do not pass
`--network` unless you intentionally opt into network probes.

## 2. Import the OpenAPI source

From the repository root (or copy `examples/refund/sources/api.yaml` into your
workspace `sources/` directory):

```bash
eac import openapi examples/refund/sources/api.yaml \
  --path refund-ws \
  --output refund-ws/facts/openapi_facts.json \
  --json
```

Expected outcome:

- Exit code `0` when the document parses.
- A facts JSON file with `SemanticFact` candidates (operation ids, status codes,
  security schemes).
- Diagnostics use `EAC1xxx` codes on parse/adapter failures (fail closed).

Validate the facts file is non-empty:

```bash
python -c "from envassure.facts.store import FactStore; print(len(FactStore.load('refund-ws/facts/openapi_facts.json')))"
```

## 3. Reconcile with other sources (optional)

The refund pack also has an approved SOP and an operational trace that conflict
with the OpenAPI 504 wording:

```bash
eac import procedure examples/refund/sources/refund-sop.md \
  --path refund-ws -o refund-ws/facts/sop_facts.json
eac import traces examples/refund/sources/trace-0187.jsonl \
  --path refund-ws -o refund-ws/facts/trace_facts.json
```

Merge facts into one store (example using Python):

```bash
python - <<'PY'
from pathlib import Path
from envassure.facts.store import FactStore
from envassure.reconciliation import reconcile

root = Path("refund-ws/facts")
facts = []
for name in ("openapi_facts.json", "sop_facts.json", "trace_facts.json"):
    facts.extend(FactStore.load(root / name).list())
result = reconcile(facts)
print("ambiguities", len(result.ambiguities))
for a in result.ambiguities:
    print(a.id, a.status, a.subject)
PY
```

Open ambiguities (hashed classic refund retry id; historical `AMB-0042` is a
fixture alias in packaged demo docs only) block
release-grade packs until an expert decision is recorded with `eac decide`.

## 4. Build IR from the manual SDK world

OpenAPI import produces facts, not a finished world. Project or author IR via
the SDK module:

```bash
eac build-ir --module examples/refund/world.py -o examples/refund/ir/world.json
eac lint examples/refund/ir/world.json
```

`eac lint` reports reference-integrity issues (`EAC3xxx`) and related analysis
codes. Until retry/timeout ambiguity is decided, expect `EAC4027` /
transaction-retry diagnostics on `submit_refund`.

## 5. Versioning and validation checklist

| Step | Command | Pass criteria |
| --- | --- | --- |
| Adapter | `eac import openapi …` | Exit 0; facts written |
| Lint | `eac lint …/world.json` | No unexpected `EAC3xxx` errors for decided worlds |
| Analyze | `eac analyze …/world.json` | Review `EAC4xxx` / `EAC5xxx` |
| Pack | `eac package … -o refund.eap` then `eac verify-pack refund.eap` | Pack OK |

Do not treat OpenAPI as a complete behavioral oracle: missing timeout/state
semantics must remain open ambiguities or explicit expert decisions.
