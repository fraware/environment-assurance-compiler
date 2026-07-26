# OpenEnv

Status: **experimental / best-effort** (Milestone C4). Upstream OpenEnv APIs
remain unstable; EnvAssure pins `openenv==0.4.1` and fails closed on unsupported
paths.

## Install

```bash
pip install 'envassure[openenv]'   # pins openenv==0.4.1 + gymnasium
```

## CLI

```bash
eac export openenv world.json --actor-id client -o ./openenv_export
eac serve openenv --dir ./openenv_export
eac openenv test --dir ./openenv_export
```

Note: top-level `eac test` remains the runtime determinism property. Use
`eac openenv test` (or `eac serve openenv` / `eac export openenv`) for OpenEnv.

| Item | Location |
| ---- | -------- |
| Adapter | `envassure.runtime.adapters.openenv_service` |
| Envelopes | `EnvAssureOpenEnvAction\|Observation\|State` |
| Codegen | `envassure.codegen.openenv_target` |
| Example | [`examples/openenv_refund/`](https://github.com/fraware/environment-assurance-compiler/tree/main/examples/openenv_refund) |
| Image | `ghcr.io/fraware/envassure-openenv:<version>` (after image qualify; deferred) |

## Limitations

- Full upstream HTTP/server protocol is not claimed; serve performs adapter smoke reset.
- Concurrent episodes use runtime `fork()` isolation.
- Same-seed reset is deterministic when the IR runtime is deterministic.

## Related

- [Gymnasium](gymnasium.md)
- [Reference-system validation](reference-system-validation.md)
