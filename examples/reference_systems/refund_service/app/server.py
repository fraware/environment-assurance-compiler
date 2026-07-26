"""Minimal refund reference service (stdlib HTTP; optional Postgres).

Endpoints:
  GET  /healthz
  POST /v1/reset
  POST /v1/probe          — black-box agent path
  GET  /v1/admin/state    — evaluator-only (requires X-EnvAssure-Evaluator)
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

EVALUATOR_TOKEN = os.environ.get("ENVASURE_EVALUATOR_TOKEN", "dev-evaluator-token")
HOST = os.environ.get("REFUND_SERVICE_HOST", "127.0.0.1")
PORT = int(os.environ.get("REFUND_SERVICE_PORT", "18080"))


class RefundStore:
    """In-memory refund state with planted mismatch hook for differential CI."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset(seed=0)

    def reset(self, seed: int | None = None) -> None:
        with self._lock:
            self.seed = seed
            self.accounts: dict[str, dict[str, Any]] = {
                "acct-1": {"balance": 1000, "currency": "USD", "role": "customer"},
                "acct-admin": {"balance": 0, "currency": "USD", "role": "approver"},
            }
            self.refunds: dict[str, dict[str, Any]] = {}
            self.idempotency: dict[str, str] = {}
            self.approvals: list[str] = []
            self.clock = 0
            self.fault_profile = {
                "timeout_actions": set(),
                "plant_mismatch": os.environ.get("PLANT_MISMATCH", "0") == "1",
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "seed": self.seed,
                "accounts": dict(self.accounts),
                "refunds": dict(self.refunds),
                "idempotency": dict(self.idempotency),
                "approvals": list(self.approvals),
                "clock": self.clock,
            }

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.clock += 1
            if action_id == "submit_refund":
                return self._submit_refund(probe_id, payload)
            if action_id == "approve_refund":
                return self._approve(probe_id, payload)
            if action_id == "get_status":
                rid = str(payload.get("refund_id") or "")
                refund = self.refunds.get(rid, {})
                return {
                    "probe_id": probe_id,
                    "success": bool(refund),
                    "observation": dict(refund),
                    "state": {"refund_id": rid, "status": refund.get("status")},
                    "authorization_ok": True,
                }
            if action_id == "get_balance":
                acct = str(payload.get("account_id") or "acct-1")
                bal = self.accounts.get(acct, {}).get("balance")
                # Planted mismatch: report balance-1 to agent observation only.
                obs_bal = bal
                if self.fault_profile["plant_mismatch"] and isinstance(bal, int):
                    obs_bal = bal - 1
                return {
                    "probe_id": probe_id,
                    "success": bal is not None,
                    "observation": {"account_id": acct, "balance": obs_bal},
                    "state": {"account_id": acct, "balance": bal},
                    "authorization_ok": True,
                    "failure_id": None if bal is not None else "unknown_account",
                }
            return {
                "probe_id": probe_id,
                "success": False,
                "failure_id": "unknown_action",
                "observation": {},
                "state": {},
            }

    def _submit_refund(self, probe_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        key = str(payload.get("idempotency_key") or "")
        amount = int(payload.get("amount") or 0)
        account_id = str(payload.get("account_id") or "acct-1")
        if key and key in self.idempotency:
            rid = self.idempotency[key]
            refund = self.refunds[rid]
            return {
                "probe_id": probe_id,
                "success": True,
                "observation": dict(refund),
                "state": dict(refund),
                "authorization_ok": True,
                "idempotent_replay_equal": True,
                "metadata": {"idempotent_hit": True},
            }
        if payload.get("inject") == "timeout":
            return {
                "probe_id": probe_id,
                "success": False,
                "failure_id": "timeout",
                "observation": {"status": "unknown"},
                "state": {"status": "unknown"},
                "authorization_ok": True,
            }
        roles = payload.get("actor_roles") or []
        if isinstance(roles, list) and roles and "customer" not in {
            str(r).removeprefix("role:") for r in roles
        }:
            return {
                "probe_id": probe_id,
                "success": False,
                "failure_id": "unauthorized",
                "authorization_ok": False,
                "observation": {},
                "state": {},
            }
        rid = f"rf-{len(self.refunds) + 1}"
        refund = {
            "refund_id": rid,
            "account_id": account_id,
            "amount": amount,
            "status": "pending",
        }
        self.refunds[rid] = refund
        if key:
            self.idempotency[key] = rid
        return {
            "probe_id": probe_id,
            "success": True,
            "observation": dict(refund),
            "state": dict(refund),
            "authorization_ok": True,
        }

    def _approve(self, probe_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        roles = {str(r).removeprefix("role:") for r in (payload.get("actor_roles") or [])}
        if "approver" not in roles and "admin" not in roles:
            return {
                "probe_id": probe_id,
                "success": False,
                "failure_id": "unauthorized",
                "authorization_ok": False,
                "observation": {},
                "state": {},
            }
        rid = str(payload.get("refund_id") or "")
        refund = self.refunds.get(rid)
        if refund is None:
            return {
                "probe_id": probe_id,
                "success": False,
                "failure_id": "not_found",
                "observation": {},
                "state": {},
            }
        acct = self.accounts.get(str(refund["account_id"]))
        if acct is not None:
            acct["balance"] = int(acct["balance"]) - int(refund["amount"])
        refund["status"] = "approved"
        self.approvals.append(rid)
        return {
            "probe_id": probe_id,
            "success": True,
            "observation": dict(refund),
            "state": dict(refund),
            "authorization_ok": True,
        }


STORE = RefundStore()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("body must be object")
        return data

    def _send(self, code: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _require_evaluator(self) -> bool:
        token = self.headers.get("X-EnvAssure-Evaluator")
        if token != EVALUATOR_TOKEN:
            self._send(403, {"error": "evaluator token required"})
            return False
        return True

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/healthz":
            self._send(200, {"ok": True, "service": "refund_service"})
            return
        if path == "/v1/admin/state":
            if not self._require_evaluator():
                return
            self._send(200, STORE.snapshot())
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            body = self._read_json()
        except (ValueError, json.JSONDecodeError) as exc:
            self._send(400, {"error": str(exc)})
            return
        if path == "/v1/reset":
            if not self._require_evaluator():
                return
            STORE.reset(seed=body.get("seed"))
            self._send(200, {"ok": True, "seed": STORE.seed})
            return
        if path == "/v1/probe":
            outcome = STORE.execute(
                str(body.get("probe_id") or ""),
                str(body.get("action_id") or ""),
                dict(body.get("payload") or {}),
            )
            self._send(200, outcome)
            return
        self._send(404, {"error": "not_found"})


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"refund_service listening on http://{HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
