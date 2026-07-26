# Codegen targets

Codegen targets turn compiled IR into locked templates or export scaffolds.
Digests are recorded in `.eac/lock.json` so rebuilds are auditable.

## Plugin kind

Register out-of-tree targets as plugins with kind `codegen_target`. See
[Plugin API](../reference/plugin-api.md) and
[Author plugins](../guides/author-plugins.md).

## Rules

1. Template changes that alter emitted digests are compatibility-sensitive —
   document them in [Compatibility](../compatibility.md) and the changelog.
2. Generated code is untrusted until verified (lint, tests, pack verify).
3. Fail closed when IR uses unsupported semantics for the target.
4. Do not claim production parity for generated services without differential
   or obligation evidence.

## Planned / in-flight targets

| Target | Status |
| ------ | ------ |
| OpenEnv scaffold | Landing with Milestone C — see [OpenEnv](../integrations/openenv.md) |
| Existing lockable templates | Follow workspace lock / package flows today |

## Related

- [Runtime adapters](runtime-adapters.md)
- [Package and publish](../guides/package-and-publish.md)
