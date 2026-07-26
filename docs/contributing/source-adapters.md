# Source adapters

How to extend EnvAssure's import surface. Prefer plugins over forking core
importers.

## Built-in kinds

| Kind | Typical input | Notes |
| ---- | ------------- | ----- |
| `openapi` | OpenAPI document | Incomplete timeout/retry must surface as ambiguities |
| `database` / `postgres` | DDL / schema dump | `[postgres]` extra |
| `policy` | Policy document | |
| `procedure` | SOP / procedure text | |
| `traces` | Trace corpora | |

CLI: `eac import <kind> <source> [--merge]`.

## Author rules

1. Emit `SemanticFact` rows with structured confidence — never bare floats as
   authority.
2. Unsupported standard features get diagnostics; do not invent defaults for
   timeout, retry, or idempotency.
3. Unresolved ambiguities stay open until `eac decide` / CEGR.
4. Optional extras fail closed when missing.

## Guides

- User-facing stub: [Author a source adapter](../guides/author-source-adapter.md)
- Concepts: [Sources and facts](../concepts/sources-and-facts.md)
- Plugins: [Author plugins](../guides/author-plugins.md)

## Related

- [Codegen targets](codegen-targets.md)
- [Defect reports](defect-reports.md)
