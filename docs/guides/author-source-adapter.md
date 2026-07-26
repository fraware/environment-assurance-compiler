# Author a source adapter

Source adapters turn operational artifacts into **SemanticFacts** with
provenance. They do not silently invent authoritative IR.

## Existing kinds

CLI: `eac import <kind> <source>` where `<kind>` is one of:

| Kind | Typical input | Package |
| ---- | ------------- | ------- |
| `openapi` | OpenAPI document | `envassure.sources.openapi` |
| `database` / `postgres` | DDL / schema dump | `sources.database`, `envassure.postgres` (extra) |
| `policy` | Policy document | `sources.policy` |
| `procedure` | SOP / procedure text | `sources.procedure` |
| `traces` | Trace corpora | `sources.traces` |

Register out-of-tree adapters as plugins (`source_adapter` kind) or via
`get_adapter` / entry points — see [Author plugins](author-plugins.md).

## Fact contract (fail-closed)

1. Emit `SemanticFact` rows with a structured `ConfidenceRecord`
   (`evidence_class`, `derivation_class`, `extractor_certainty`) — never a bare
   float confidence.
2. Emit diagnostics for unsupported standard features; missing timeout / retry /
   idempotency must surface as ambiguities in reconciliation, not invented
   defaults.
3. Never project unresolved ambiguities into release IR without
   `eac decide` / CEGR expert decisions.
4. Optional extras (`postgres`, `model-assisted`) must fail closed with
   `EAC9003` / import errors when the extra is absent.

## Related

- [Sources and facts](../concepts/sources-and-facts.md)
- [Build from OpenAPI](build-from-openapi.md)
- [Report an environment defect](report-environment-defect.md)
- [Reconciliation / CEGR](../concepts/ambiguities-and-decisions.md)
