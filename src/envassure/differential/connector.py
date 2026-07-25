"""Reference connector protocol and concrete offline/opt-in implementations.

Plugging a real reference
-------------------------
1. Implement :class:`ReferenceConnector` (``name``, ``reset``, ``execute``).
2. Prefer :class:`RecordedFixtureConnector` for CI — replay canned
   ``ProbeOutcome`` records from JSON with **no network**.
3. Prefer :class:`FileBackedSimulatorConnector` for a local state-machine
   simulator (counter / refund) driven by a JSON definition file.
4. Use :class:`SubprocessReferenceConnector` for an offline local process
   that speaks JSON lines on stdin/stdout (still no network).
5. Use :class:`LocalHttpStubConnector` only with ``allow_network=True`` against
   a local loopback stub you control; remote hosts are rejected.
6. Wire via ``eac differential --fixture …`` / ``--simulator …`` or Python.

Network access is **off by default**. Connectors that talk to HTTP must be
constructed with ``allow_network=True`` and may only target loopback.
"""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field


class ProbeOutcome(BaseModel):
    """Normalized outcome from a reference or compiled environment."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str
    success: bool
    observation: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    failure_id: str | None = None
    authorization_ok: bool | None = None
    latency_ms: float | None = None
    retry_count: int = 0
    idempotent_replay_equal: bool | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ReferenceConnector(Protocol):
    """Protocol for differential validation against an external reference."""

    def name(self) -> str:
        """Human-readable connector name."""

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        """Execute one probe step against the reference."""

    def reset(self, seed: int | None = None) -> None:
        """Reset reference episode state."""


def _coerce_outcome(key: str, value: ProbeOutcome | dict[str, Any]) -> ProbeOutcome:
    if isinstance(value, ProbeOutcome):
        return value
    data = dict(value)
    data.setdefault("probe_id", key)
    return ProbeOutcome.model_validate(data)


class InMemoryReferenceConnector:
    """
    Deterministic in-memory reference for tests and offline differential runs.

    Scripts map ``(probe_id, action_id)`` or ``action_id`` to canned ProbeOutcome
    factories / dicts.
    """

    def __init__(
        self,
        *,
        connector_name: str = "in_memory",
        scripts: dict[str, ProbeOutcome | dict[str, Any]] | None = None,
        default_success: bool = True,
    ) -> None:
        self._name = connector_name
        self._scripts: dict[str, ProbeOutcome] = {}
        for key, value in (scripts or {}).items():
            self._scripts[key] = _coerce_outcome(key, value)
        self._default_success = default_success
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._history.clear()

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        self._history.append((probe_id, action_id))
        for key in (f"{probe_id}:{action_id}", probe_id, action_id):
            if key in self._scripts:
                outcome = self._scripts[key].model_copy(deep=True)
                outcome.probe_id = probe_id
                outcome.metadata = {
                    **outcome.metadata,
                    "payload": payload,
                    "seed": self._seed,
                }
                return outcome
        return ProbeOutcome(
            probe_id=probe_id,
            success=self._default_success,
            observation={"echo": payload},
            state={},
            metadata={"synthetic": True, "action_id": action_id},
        )

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._history)


class RecordedFixtureConnector:
    """
    Replay reference responses from a recorded fixture file or in-memory records.

    Fixture JSON schema::

        {
          "connector_name": "recorded",
          "records": [
            {
              "probe_id": "normal.increment",
              "action_id": "increment",
              "outcome": { "success": true, "observation": {"count": 1}, ... }
            }
          ]
        }

    Lookup order per execute: exact (probe_id, action_id), then probe_id, then
    action_id, then sequential cursor (for ordered replays).
    """

    def __init__(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        fixture_path: Path | str | None = None,
        connector_name: str = "recorded_fixture",
        default_success: bool = False,
    ) -> None:
        loaded_name = connector_name
        loaded_records = list(records or [])
        if fixture_path is not None:
            path = Path(fixture_path)
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("fixture root must be a JSON object")
            loaded_name = str(raw.get("connector_name") or connector_name)
            items = raw.get("records")
            if not isinstance(items, list):
                raise ValueError("fixture.records must be a list")
            loaded_records = [item for item in items if isinstance(item, dict)]
        self._name = loaded_name
        self._records = loaded_records
        self._default_success = default_success
        self._cursor = 0
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []
        self._by_key: dict[str, ProbeOutcome] = {}
        for item in self._records:
            probe_id = str(item.get("probe_id") or "")
            action_id = str(item.get("action_id") or "")
            outcome_raw = item.get("outcome") or item
            if not isinstance(outcome_raw, dict):
                continue
            outcome = _coerce_outcome(probe_id or action_id or "record", outcome_raw)
            if probe_id and action_id:
                self._by_key[f"{probe_id}:{action_id}"] = outcome
            if probe_id:
                self._by_key.setdefault(probe_id, outcome)
            if action_id:
                self._by_key.setdefault(action_id, outcome)

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._cursor = 0
        self._history.clear()

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        self._history.append((probe_id, action_id))
        for key in (f"{probe_id}:{action_id}", probe_id, action_id):
            if key in self._by_key:
                outcome = self._by_key[key].model_copy(deep=True)
                outcome.probe_id = probe_id
                outcome.metadata = {
                    **outcome.metadata,
                    "payload": payload,
                    "seed": self._seed,
                    "source": "fixture_key",
                }
                return outcome
        if self._cursor < len(self._records):
            item = self._records[self._cursor]
            self._cursor += 1
            outcome_raw = item.get("outcome") or item
            if isinstance(outcome_raw, dict):
                outcome = _coerce_outcome(probe_id, outcome_raw)
                outcome.probe_id = probe_id
                outcome.metadata = {
                    **outcome.metadata,
                    "payload": payload,
                    "seed": self._seed,
                    "source": "fixture_cursor",
                    "cursor": self._cursor - 1,
                }
                return outcome
        return ProbeOutcome(
            probe_id=probe_id,
            success=self._default_success,
            failure_id="fixture_miss",
            metadata={
                "synthetic": True,
                "action_id": action_id,
                "source": "fixture_miss",
            },
        )

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._history)


class FileBackedSimulatorConnector:
    """
    Offline file-backed state-machine simulator.

    Simulator JSON schema::

        {
          "connector_name": "counter_sim",
          "kind": "counter",
          "initial_state": {"count": 0},
          "authorization": {
            "reset": {"required_roles": ["admin"], "failure_id": "unauthorized"}
          },
          "actions": {
            "increment": {"effect": "count += 1"},
            "reset": {"effect": "count = 0"},
            "get": {"effect": "noop"}
          }
        }

    Supported ``kind`` values: ``counter``, ``refund``, ``generic``.
    Effects are a small DSL: ``var += N``, ``var = N``, ``noop``.
    """

    def __init__(
        self,
        *,
        definition: dict[str, Any] | None = None,
        definition_path: Path | str | None = None,
        connector_name: str = "file_backed_sim",
    ) -> None:
        if definition is None and definition_path is None:
            raise ValueError("definition or definition_path is required")
        if definition_path is not None:
            raw = json.loads(Path(definition_path).read_text(encoding="utf-8-sig"))
            if not isinstance(raw, dict):
                raise ValueError("simulator definition must be a JSON object")
            definition = raw
        assert definition is not None
        self._def = definition
        self._name = str(definition.get("connector_name") or connector_name)
        self._kind = str(definition.get("kind") or "generic")
        self._initial = dict(definition.get("initial_state") or {})
        self._actions = dict(definition.get("actions") or {})
        self._auth = dict(definition.get("authorization") or {})
        self._state: dict[str, Any] = dict(self._initial)
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._state = dict(self._initial)
        self._history.clear()

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        self._history.append((probe_id, action_id))
        sequence = payload.get("sequence") or payload.get("pair")
        if isinstance(sequence, list) and sequence:
            last = ProbeOutcome(probe_id=probe_id, success=True, state=dict(self._state))
            for step in sequence:
                last = self._apply_action(probe_id, str(step), payload)
                if not last.success:
                    return last
            last.metadata = {
                **last.metadata,
                "source": "file_backed_sim",
                "sequence": sequence,
            }
            return last
        return self._apply_action(probe_id, action_id, payload)

    def _apply_action(
        self,
        probe_id: str,
        action_id: str,
        payload: dict[str, Any],
    ) -> ProbeOutcome:
        auth = self._auth.get(action_id)
        if isinstance(auth, dict):
            required = [str(r) for r in auth.get("required_roles") or []]
            roles = payload.get("actor_roles")
            if roles is None:
                roles = []
            if not isinstance(roles, list):
                roles = []
            normalized = {str(r).removeprefix("role:") for r in roles}
            needed = {r.removeprefix("role:") for r in required}
            if needed and not (normalized & needed):
                return ProbeOutcome(
                    probe_id=probe_id,
                    success=False,
                    failure_id=str(auth.get("failure_id") or "unauthorized"),
                    authorization_ok=False,
                    state=dict(self._state),
                    observation=dict(self._state),
                    metadata={"source": "file_backed_sim", "action_id": action_id},
                )

        spec = self._actions.get(action_id)
        if spec is None and self._kind == "counter":
            spec = _default_counter_action(action_id)
        if spec is None and self._kind == "refund":
            spec = _default_refund_action(action_id)
        if spec is None:
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="unknown_action",
                state=dict(self._state),
                metadata={"source": "file_backed_sim", "action_id": action_id},
            )

        effect = str(spec.get("effect") if isinstance(spec, dict) else spec)
        self._apply_effect(effect, payload)
        success = True
        failure_id = None
        if (
            self._kind == "refund"
            and action_id == "submit_refund"
            and payload.get("inject") == "timeout"
        ):
            success = False
            failure_id = "timeout"
            self._state["status"] = "committed"
            self._state["timeout_seen"] = True

        return ProbeOutcome(
            probe_id=probe_id,
            success=success,
            failure_id=failure_id,
            authorization_ok=True,
            observation=dict(self._state),
            state=dict(self._state),
            metadata={
                "source": "file_backed_sim",
                "action_id": action_id,
                "seed": self._seed,
                "kind": self._kind,
            },
        )

    def _apply_effect(self, effect: str, payload: dict[str, Any]) -> None:
        effect = effect.strip()
        if effect in {"", "noop"}:
            return
        if "+=" in effect:
            left, right = effect.split("+=", 1)
            key = left.strip()
            delta = _eval_num(right.strip(), payload)
            current = self._state.get(key, 0)
            if isinstance(current, int | float):
                self._state[key] = current + delta
            else:
                self._state[key] = delta
            return
        if "=" in effect:
            left, right = effect.split("=", 1)
            key = left.strip()
            raw = right.strip()
            if raw in payload:
                self._state[key] = payload[raw]
            elif _is_number(raw):
                self._state[key] = _eval_num(raw, payload)
            else:
                self._state[key] = raw.strip("\"'")

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._history)

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)


def _default_counter_action(action_id: str) -> dict[str, str] | None:
    defaults = {
        "increment": {"effect": "count += 1"},
        "reset": {"effect": "count = 0"},
        "get": {"effect": "noop"},
    }
    return defaults.get(action_id)


def _default_refund_action(action_id: str) -> dict[str, str] | None:
    defaults = {
        "submit_refund": {"effect": "status = committed"},
        "get_status": {"effect": "noop"},
    }
    return defaults.get(action_id)


def _is_number(raw: str) -> bool:
    try:
        float(raw)
        return True
    except ValueError:
        return False


def _eval_num(raw: str, payload: dict[str, Any]) -> float | int:
    if raw in payload and isinstance(payload[raw], int | float):
        return payload[raw]  # type: ignore[no-any-return]
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return int(raw)
    return float(raw)


class SubprocessReferenceConnector:
    """
    Offline local subprocess connector (JSON request/response on stdin/stdout).

    Does **not** use the network. The child process must:

    - Read one JSON object from stdin
    - Write one ProbeOutcome-shaped JSON object to stdout

    Construction requires ``allow_subprocess=True`` (fail-closed otherwise).
    """

    def __init__(
        self,
        command: list[str],
        *,
        allow_subprocess: bool = False,
        connector_name: str = "subprocess_reference",
        timeout_s: float = 5.0,
        cwd: Path | str | None = None,
    ) -> None:
        if not allow_subprocess:
            raise PermissionError(
                "SubprocessReferenceConnector requires allow_subprocess=True "
                "(subprocess execution is off by default)"
            )
        if not command:
            raise ValueError("command must be a non-empty list")
        self._command = list(command)
        self._name = connector_name
        self._timeout_s = timeout_s
        self._cwd = str(cwd) if cwd is not None else None
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._history.clear()

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        self._history.append((probe_id, action_id))
        request = json.dumps(
            {
                "probe_id": probe_id,
                "action_id": action_id,
                "payload": payload,
                "seed": self._seed,
            }
        )
        try:
            completed = subprocess.run(
                self._command,
                input=request,
                capture_output=True,
                text=True,
                timeout=self._timeout_s,
                cwd=self._cwd,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="subprocess_error",
                metadata={"error": str(exc), "action_id": action_id},
            )
        if completed.returncode != 0:
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="subprocess_nonzero",
                metadata={
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-500:],
                    "action_id": action_id,
                },
            )
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="subprocess_bad_json",
                metadata={"error": str(exc), "stdout": completed.stdout[:500]},
            )
        if not isinstance(raw, dict):
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="subprocess_bad_payload",
            )
        outcome = _coerce_outcome(probe_id, raw)
        outcome.probe_id = probe_id
        outcome.metadata = {**outcome.metadata, "source": "subprocess"}
        return outcome

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._history)


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class LocalHttpStubConnector:
    """
    Opt-in HTTP connector restricted to loopback hosts.

    Posts JSON ``{"probe_id", "action_id", "payload", "seed"}`` to ``base_url``
    and expects a ProbeOutcome JSON body. Raises if ``allow_network`` is false
    or if the URL host is not loopback.
    """

    def __init__(
        self,
        base_url: str,
        *,
        allow_network: bool = False,
        connector_name: str = "local_http_stub",
        timeout_s: float = 2.0,
    ) -> None:
        if not allow_network:
            raise PermissionError(
                "LocalHttpStubConnector requires allow_network=True (network is off by default)"
            )
        parsed = urlparse(base_url)
        host = (parsed.hostname or "").lower()
        if host not in _LOOPBACK_HOSTS:
            raise PermissionError(
                f"LocalHttpStubConnector refuses non-loopback host {host!r}; "
                "use RecordedFixtureConnector for offline replay"
            )
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"unsupported URL scheme: {parsed.scheme!r}")
        self._base_url = base_url.rstrip("/")
        self._name = connector_name
        self._timeout_s = timeout_s
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._history.clear()

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        self._history.append((probe_id, action_id))
        body = json.dumps(
            {
                "probe_id": probe_id,
                "action_id": action_id,
                "payload": payload,
                "seed": self._seed,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._base_url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="http_unreachable",
                metadata={"error": str(exc), "action_id": action_id},
            )
        if not isinstance(raw, dict):
            return ProbeOutcome(
                probe_id=probe_id,
                success=False,
                failure_id="http_bad_payload",
                metadata={"action_id": action_id},
            )
        outcome = _coerce_outcome(probe_id, raw)
        outcome.probe_id = probe_id
        outcome.metadata = {**outcome.metadata, "source": "local_http_stub"}
        return outcome

    @property
    def history(self) -> list[tuple[str, str]]:
        return list(self._history)
