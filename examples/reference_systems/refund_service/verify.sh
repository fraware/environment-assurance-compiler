#!/usr/bin/env bash
# Verify E3 refund reference service contract files + planted-mismatch behavior.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED="${ROOT}/expected/service-contract.json"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi
# shellcheck source=../../_python.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/_python.sh"

if [[ ! -f "${EXPECTED}" ]]; then
  echo "error: missing ${EXPECTED}" >&2
  exit 1
fi

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
expected = json.loads((root / "expected" / "service-contract.json").read_text(encoding="utf-8"))
for name in expected["required_files"]:
    assert (root / name).exists(), name

server = root / "app" / "server.py"
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])

env = {
    **os.environ,
    "REFUND_SERVICE_HOST": "127.0.0.1",
    "REFUND_SERVICE_PORT": str(port),
    "ENVASURE_EVALUATOR_TOKEN": "test-token",
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
    while time.time() < deadline:
        try:
            conn = HttpReferenceConnector(
                base,
                allow_network=True,
                privileged_token="test-token",
            )
            if conn.doctor().get("ok"):
                break
        except Exception:
            time.sleep(0.1)
            conn = None
    if conn is None:
        raise SystemExit("refund service failed to start")
    conn.reset(seed=1)
    out = conn.execute("p1", "get_balance", {"account_id": "acct-1"})
    priv = conn.probe_state()
    assert out.observation.get("balance") == expected["planted_observation_balance"]
    assert priv["accounts"]["acct-1"]["balance"] == expected["authoritative_balance"]
    print("ok planted mismatch detected")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
PY

if [[ "${ENVASURE_RUN_COMPOSE:-}" == "1" ]] && command -v docker >/dev/null 2>&1; then
  docker compose -f docker-compose.yml config >/dev/null
else
  echo "notice: compose verify skipped (ENVASURE_RUN_COMPOSE!=1 or no docker)"
fi

echo "verify.sh passed"
