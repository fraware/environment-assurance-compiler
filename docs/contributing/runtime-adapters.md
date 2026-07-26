# Runtime adapters

Adapters expose the reference runtime (`EventSourcedEnvironment`) to external
frameworks. Base wheel stays light; adapters live behind extras and fail closed
when dependencies are missing.

## Existing

| Adapter | Extra | Status |
| ------- | ----- | ------ |
| Gymnasium | `[gym]` | Path exists; release-qualified subclass track is Milestone C |
| PettingZoo | `[pettingzoo]` | **Experimental** — not a beta conformance claim |

User guide: [Author a runtime extension](../guides/author-runtime-extension.md).

## Landing (Milestone C)

| Adapter | Extra | Docs |
| ------- | ----- | ---- |
| Gymnasium qualify | `[gym]` | [Gymnasium](../integrations/gymnasium.md) |
| OpenEnv service | `[openenv]` | [OpenEnv](../integrations/openenv.md) |

## Author checklist

1. Surface typed failures for unsupported semantics — never invent success.
2. Preserve truncated vs terminated (and framework-specific terminal signals).
3. Keep network / subprocess opt-in.
4. Document fidelity limits on the integration page; interface conformance ≠
   fidelity evidence.
5. Prefer shared protocols (for example reward providers) over one-off forks.

## Related

- [Runtime and snapshots](../concepts/runtime-and-snapshots.md)
- [Codegen targets](codegen-targets.md)
- [Threat model](../security/threat-model.md)
