"""HTTP black-box reference system connector (evaluator-privileged probes)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from envassure.differential.connector import ProbeOutcome, _LOOPBACK_HOSTS, _coerce_outcome


class ReferenceSystemConnectorError(ValueError):
    """Fail-closed connector configuration / protocol error."""


class HttpReferenceConnector:
    """Black-box HTTP connector for differential validation against a reference service.

    Agent path (``execute``) posts probe actions to ``{base_url}/v1/probe``.
    Privileged evaluator path (``probe_state``) hits ``{base_url}/v1/admin/state``
    and must never be exposed to the agent under test.
    """

    def __init__(
        self,
        base_url: str,
        *,
        allow_network: bool = False,
        allow_non_loopback: bool = False,
        connector_name: str = "http_reference",
        timeout_s: float = 5.0,
        privileged_token: str | None = None,
    ) -> None:
        if not allow_network:
            raise PermissionError(
                "HttpReferenceConnector requires allow_network=True "
                "(network access is off by default)"
            )
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower()
        if not allow_non_loopback and host not in _LOOPBACK_HOSTS:
            raise PermissionError(
                f"HttpReferenceConnector refuses non-loopback host {host!r}; "
                "pass allow_non_loopback=True only for controlled CI services"
            )
        if parsed.scheme not in {"http", "https"}:
            raise ReferenceSystemConnectorError(f"unsupported URL scheme: {parsed.scheme!r}")
        self._base_url = base_url.rstrip("/")
        self._name = connector_name
        self._timeout_s = timeout_s
        self._privileged_token = privileged_token
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._history.clear()
        self._post_json(
            "/v1/reset",
            {"seed": seed},
            headers=self._privileged_headers(),
        )

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        """Black-box agent path — no privileged headers."""
        self._history.append((probe_id, action_id))
        started = time.perf_counter()
        raw = self._post_json(
            "/v1/probe",
            {
                "probe_id": probe_id,
                "action_id": action_id,
                "payload": payload,
                "seed": self._seed,
            },
        )
        latency_ms = (time.perf_counter() - started) * 1000.0
        if not isinstance(raw, dict):
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="http_bad_payload",
                latency_ms=latency_ms,
                metadata={"action_id": action_id},
            )
        outcome = _coerce_outcome(probe_id, raw)
        outcome.probe_id = probe_id
        outcome.latency_ms = latency_ms if outcome.latency_ms is None else outcome.latency_ms
        outcome.metadata = {**outcome.metadata, "source": "http_reference"}
        return outcome

    def probe_state(self) -> dict[str, Any]:
        """Evaluator-only privileged state probe (never on the agent path)."""
        raw = self._get_json("/v1/admin/state", headers=self._privileged_headers())
        if not isinstance(raw, dict):
            raise ReferenceSystemConnectorError("privileged state probe returned non-object")
        return raw

    def doctor(self) -> dict[str, Any]:
        """Health check against ``/healthz`` (and optional privileged probe)."""
        checks: dict[str, Any] = {"connector": self._name, "base_url": self._base_url}
        try:
            health = self._get_json("/healthz")
            checks["healthz"] = {"ok": True, "body": health}
        except Exception as exc:  # noqa: BLE001 — doctor aggregates failures
            checks["healthz"] = {"ok": False, "error": str(exc)}
        try:
            state = self.probe_state()
            checks["privileged_state"] = {"ok": True, "keys": sorted(state.keys())}
        except Exception as exc:  # noqa: BLE001
            checks["privileged_state"] = {"ok": False, "error": str(exc)}
        checks["ok"] = bool(checks["healthz"].get("ok")) and bool(
            checks["privileged_state"].get("ok")
        )
        return checks

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._history)

    def _privileged_headers(self) -> dict[str, str]:
        if not self._privileged_token:
            return {}
        return {"X-EnvAssure-Evaluator": self._privileged_token}

    def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> Any:
        data = json.dumps(body).encode("utf-8")
        hdrs = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            data=data,
            headers=hdrs,
            method="POST",
        )
        return self._open(request)

    def _get_json(self, path: str, *, headers: dict[str, str] | None = None) -> Any:
        hdrs = {"Accept": "application/json", **(headers or {})}
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            headers=hdrs,
            method="GET",
        )
        return self._open(request)

    def _open(self, request: urllib.request.Request) -> Any:
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:500]
            raise ReferenceSystemConnectorError(
                f"HTTP {exc.code} for {request.full_url}: {body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ReferenceSystemConnectorError(f"unreachable {request.full_url}: {exc}") from exc
