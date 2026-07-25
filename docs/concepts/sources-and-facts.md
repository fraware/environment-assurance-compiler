# Sources and facts

EnvAssure separates **evidence** (sources) from **claims** (semantic facts) from
**decisions** (expert resolutions).

## Source artifacts

Sources are declared in `sources.yml` as `SourceArtifact` records:

- identity and path
- **authority class** (controlled vocabulary, for example `api_contract`,
  `operational_trace`, `approved_procedure`, `expert_decision`,
  `model_proposal`)
- completeness declaration
- content digest (canonical)

Malformed or unknown authority values fail closed (`EAC1001`, `EAC1002`).
Parse failures emit `EAC1004`; unknown adapter kinds emit `EAC1005`.

## Adapters

Built-in import kinds (via `eac import`):

| Kind | Typical input |
| ---- | ------------- |
| `openapi` | OpenAPI YAML/JSON |
| `database` | SQL DDL / schema dump |
| `policy` | Structured policy documents |
| `procedure` | Markdown / SOP text |
| `traces` | Streaming JSONL operational traces |

Adapters emit **candidate** `SemanticFact` records — they do not silently invent
missing timeout, retry, or idempotency semantics.

## Fact store and reconciliation

Facts accumulate under the workspace `facts/` directory. Reconciliation detects:

- conflicts (`EAC2002`)
- aliases (`EAC2003`)
- missing retry when timeouts exist (`EAC4027`)

Conflicts become open [ambiguities](ambiguities-and-decisions.md). Model-assisted
proposals use authority `model_proposal` and are never authoritative without an
expert acceptance path
([ADR-0003](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0003-provenance-mandatory.md)).

## Related commands

```bash
eac import openapi path/to/api.yaml --path . -o facts/openapi.json
eac facts --reconcile
eac ambiguities
```
