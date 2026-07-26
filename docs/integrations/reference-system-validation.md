# Reference-system validation

Status: **available** for the HTTP connector + refund reference service
(Milestone C3). Compose-backed Postgres CI is structured but may be skipped
when Docker is unavailable.

## Install / run

Offline fixtures remain the default. HTTP is opt-in:

```bash
python examples/reference_systems/refund_service/app/server.py
eac connector doctor --http-url http://127.0.0.1:18080 --allow-network --token dev-evaluator-token
eac differential run world.json --http-url http://127.0.0.1:18080 --allow-network --max-probes 100
eac differential reproduce bundle.json --ir world.json
```

| Item | Notes |
| ---- | ----- |
| Connector | `HttpReferenceConnector` — black-box `/v1/probe`; privileged `/v1/admin/state` |
| Example | [`examples/reference_systems/refund_service/`](https://github.com/fraware/environment-assurance-compiler/tree/main/examples/reference_systems/refund_service) |
| Compose | `docker-compose.yml` + Postgres; set `ENVASURE_RUN_COMPOSE=1` in CI |
| Planted mismatch | `PLANT_MISMATCH=1` diverges observation vs privileged state |

## What is not claimed

- Differential match ≠ production parity.
- Missing privileged evidence → indeterminate (not a silent match).

## Related

- [Differentially validate](../guides/differentially-validate.md)
- [Fidelity claims](../guides/fidelity-claims.md)
