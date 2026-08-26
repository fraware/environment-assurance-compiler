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

### Observation versus canonical semantics

Fact predicates encode a claim's subject as well as its value. Repeated empirical
observations must therefore not be represented as mutually exclusive definitions
of an action.

The trace adapter uses a distinct `trace_event` entity for every JSONL event and
links it to its action with `observed_action`. Event-local predicates such as
`observed_outcome`, `observed_timeout`, and `observed_state_effect` are marked
`derivation_class=observed`. Different outcomes across different events can
coexist without becoming an `EAC2002` action-semantic conflict.

A trace may support a separate action-level inference. For example, when a commit
is observed after a prior timeout for the same action, the adapter can infer that
an unconditional retry is unsafe without an idempotency guard. Such facts use
`derivation_class=inferred`; they are not relabeled as direct observations.

The same distinction applies to procedures. A procedure that merely mentions
timeout or idempotency contributes evidence-layer acknowledgement facts; it does
not define canonical `timeout_behavior` or `idempotency` unless the text actually
supports such a semantic interpretation. A concrete retry instruction can still
produce a canonical `retry_behavior` candidate.

This boundary matters for construct validity: reconciliation should compare
alternative claims about the **same semantic proposition**, not manufacture a
conflict from heterogeneous observations or from evidence that addresses
neighboring propositions.

### OpenAPI supported matrix (0.2)

| Construct | Status |
| --------- | ------ |
| Paths + HTTP methods, `operationId` | Supported (direct) |
| Local `$ref` under `#/components` | Supported |
| Path-level parameter inheritance | Supported |
| Request/response `content` media types | Supported |
| Operation + document-level `security` | Supported |
| `components.schemas` / `securitySchemes` | Supported |
| Remote `$ref`, circular `$ref` | Unsupported (`EAC1006`) |
| `callbacks`, `links`, `webhooks` | Unsupported (`EAC1006`) |

Confidence is never uniform: direct excerpts use high/medium certainty with
`derivation_class=direct`; observations use `derivation_class=observed`; inferred
hints (for example HTTP 504 → timeout behavior) use medium/low certainty with
`derivation_class=inferred`.

## Fact store and reconciliation

Facts accumulate under the workspace `facts/` directory. Reconciliation detects:

- conflicts (`EAC2002`) between distinct candidate values for the same semantic
  proposition
- aliases (`EAC2003`)
- missing retry when canonical timeout semantics exist (`EAC4027`)

Conflicts become open [ambiguities](ambiguities-and-decisions.md). Model-assisted
proposals use authority `model_proposal` and are never authoritative without an
expert acceptance path
([ADR-0003](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0003-provenance-mandatory.md)).

Only `accepted_facts` are eligible for authoritative semantic projection. A
reconciler ordering preference is not a decision, and an observation about a
specific trace event must not be silently generalized into an action definition.

## Related commands

```bash
eac import openapi path/to/api.yaml --path . -o facts/openapi.json
eac facts --reconcile
eac ambiguities
```
