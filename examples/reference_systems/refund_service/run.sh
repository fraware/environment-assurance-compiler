#!/usr/bin/env bash
# Run E3 refund reference service (stdlib HTTP; Docker compose optional).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ROOT}/.example-out"
mkdir -p "${OUT_DIR}"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi
# shellcheck source=../../_python.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/_python.sh"

echo "==> eac --version"
eac --version

echo "==> start in-process refund service + connector doctor"
"$PYTHON_BIN" - <<'PY'
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from envassure.differential.http_connector import HttpReferenceConnector

root = Path(".").resolve()
out = root / ".example-out"
server = root / "app" / "server.py"

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])

env = {
    **os.environ,
    "REFUND_SERVICE_HOST": "127.0.0.1",
    "REFUND_SERVICE_PORT": str(port),
    "ENVASURE_EVALUATOR_TOKEN": "dev-evaluator-token",
    "PLANT_MISMATCH": "1",
}
proc = subprocess.Popen(
    [sys.executable, str(server)],
    env=env,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
base = f"http://127.0.0.1:{port}"
try:
    deadline = time.time() + 10
    conn = None
    health = None
    while time.time() < deadline:
        try:
            conn = HttpReferenceConnector(
                base,
                allow_network=True,
                privileged_token="dev-evaluator-token",
            )
            health = conn.doctor()
            if health.get("ok"):
                break
        except Exception:
            time.sleep(0.1)
            conn = None
            health = None
    if conn is None or not health or not health.get("ok"):
        raise SystemExit("refund service failed to start")
    (out / "doctor.json").write_text(json.dumps(health, indent=2) + "\n", encoding="utf-8")
    print("doctor ok", base)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
PY

if [[ "${ENVASURE_RUN_COMPOSE:-}" == "1" ]] && command -v docker >/dev/null 2>&1; then
  echo "==> docker compose config (ENVASURE_RUN_COMPOSE=1)"
  docker compose -f docker-compose.yml config >/dev/null
else
  echo "notice: compose not exercised (set ENVASURE_RUN_COMPOSE=1 when Docker is available)"
fi

echo "run.sh completed; artifacts under ${OUT_DIR}"
