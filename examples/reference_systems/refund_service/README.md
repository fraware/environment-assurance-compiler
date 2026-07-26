# Refund reference system (E3)

HTTP + optional Postgres reference for differential validation.

## Local (no Docker)

```bash
python examples/reference_systems/refund_service/app/server.py
eac connector doctor --http-url http://127.0.0.1:18080 --allow-network --token dev-evaluator-token
eac differential run examples/counter/world.json --http-url http://127.0.0.1:18080 --allow-network --max-probes 100
```

## Compose

```bash
docker compose -f examples/reference_systems/refund_service/docker-compose.yml up --build -d
PLANT_MISMATCH=1 docker compose -f examples/reference_systems/refund_service/docker-compose.yml up --build -d
```

Set `PLANT_MISMATCH=1` so `get_balance` observations diverge from privileged state
(dimensions reported separately; missing evidence → indeterminate).

## Notes

- Agent path: `POST /v1/probe` (no evaluator token)
- Privileged path: `GET /v1/admin/state` + `POST /v1/reset` (token required)
- Postgres is provisioned by compose; the stdlib server currently uses in-memory state
  and is sufficient for connector/differential CI when Docker is unavailable
  (tests skip compose automatically).
