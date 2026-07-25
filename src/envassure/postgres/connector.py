"""Postgres reference connector (live DB opt-in; offline via injected connection).

Default CI never opens a real Postgres server. Tests inject a stub connection
or exercise the fail-closed extra gate. Live use requires:

* ``pip install 'envassure[postgres]'``
* ``allow_live=True``
* a DSN or an injected connection factory
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from envassure.differential.connector import ProbeOutcome
from envassure.postgres._extra import require_postgres_extra


class _SupportsExecute(Protocol):
    def execute(self, query: str, params: Any = None) -> Any: ...

    def fetchone(self) -> Any: ...

    def close(self) -> None: ...


class _SupportsConnection(Protocol):
    def cursor(self) -> _SupportsExecute: ...

    def close(self) -> None: ...

    def commit(self) -> None: ...


ConnectionFactory = Callable[[], _SupportsConnection]


class PostgresReferenceConnector:
    """Differential :class:`~envassure.differential.connector.ReferenceConnector`
    backed by Postgres when explicitly configured.

    Without ``allow_live=True`` construction fails closed. Network/live server
    access is never implied by the default test suite.
    """

    def __init__(
        self,
        *,
        dsn: str | None = None,
        connection_factory: ConnectionFactory | None = None,
        allow_live: bool = False,
        connector_name: str = "postgres",
        reset_sql: str = "SELECT 1",
        execute_sql: str | None = None,
    ) -> None:
        require_postgres_extra()
        if not allow_live and connection_factory is None:
            raise PermissionError(
                "PostgresReferenceConnector refuses live access without "
                "allow_live=True (or an injected connection_factory for tests)"
            )
        if connection_factory is None and not dsn:
            raise ValueError("PostgresReferenceConnector requires dsn= or connection_factory=")
        self._dsn = dsn
        self._factory = connection_factory
        self._allow_live = allow_live
        self._name = connector_name
        self._reset_sql = reset_sql
        self._execute_sql = execute_sql or (
            "SELECT %(probe_id)s::text AS probe_id, %(action_id)s::text AS action_id"
        )
        self._conn: _SupportsConnection | None = None
        self._seed: int | None = None
        self._history: list[tuple[str, str]] = []

    def name(self) -> str:
        return self._name

    def reset(self, seed: int | None = None) -> None:
        self._seed = seed
        self._history.clear()
        conn = self._ensure_connection()
        cur = conn.cursor()
        try:
            cur.execute(self._reset_sql)
            if hasattr(conn, "commit"):
                conn.commit()
        finally:
            cur.close()

    def execute(self, probe_id: str, action_id: str, payload: dict[str, Any]) -> ProbeOutcome:
        self._history.append((probe_id, action_id))
        conn = self._ensure_connection()
        cur = conn.cursor()
        try:
            params = {
                "probe_id": probe_id,
                "action_id": action_id,
                "payload": payload,
                "seed": self._seed,
            }
            cur.execute(self._execute_sql, params)
            row = cur.fetchone()
            if hasattr(conn, "commit"):
                conn.commit()
        finally:
            cur.close()
        observation: dict[str, Any]
        if row is None:
            observation = {}
        elif isinstance(row, dict):
            observation = dict(row)
        else:
            observation = {"row": list(row)}
        return ProbeOutcome(
            probe_id=probe_id,
            success=True,
            observation=observation,
            state={"seed": self._seed},
            metadata={
                "action_id": action_id,
                "payload": payload,
                "connector": self._name,
                "live": self._allow_live and self._factory is None,
            },
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _ensure_connection(self) -> _SupportsConnection:
        if self._conn is not None:
            return self._conn
        if self._factory is not None:
            self._conn = self._factory()
            return self._conn
        psycopg = require_postgres_extra()
        # Live path — only reached when allow_live=True and dsn provided.
        self._conn = psycopg.connect(self._dsn)
        return self._conn
