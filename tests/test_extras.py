"""Optional extras gates: postgres and model-assisted (offline)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from envassure.model_assisted.providers import (
    MODEL_ASSISTED_IMPORT_ERROR,
    get_provider,
    list_provider_entry_points,
    require_model_assisted_extra,
)
from envassure.postgres import POSTGRES_IMPORT_ERROR, parse_postgres_ddl
from envassure.postgres.ddl import PostgresDDLAdapter
from envassure.sources import get_adapter, import_source_report
from envassure.workspace.doctor import run_doctor

REPO = Path(__file__).resolve().parents[1]
PG_SQL = REPO / "tests" / "fixtures" / "postgres" / "sample_schema.sql"


def test_parse_postgres_ddl_offline_no_psycopg() -> None:
    tables = parse_postgres_ddl(PG_SQL.read_text(encoding="utf-8"))
    assert len(tables) == 2
    accounts = tables[0]
    assert accounts["schema"] == "app"
    assert accounts["table"] == "accounts"
    col_types = {c["name"]: c["type"] for c in accounts["columns"]}  # type: ignore[index]
    assert col_types["id"] == "UUID"
    assert col_types["email"].startswith("VARCHAR")
    assert col_types["meta"] == "JSONB"
    assert (
        "TIMESTAMPTZ" in col_types["created_at"]
        or "TIMESTAMP WITH TIME ZONE" in col_types["created_at"]
    )
    orders = tables[1]
    assert orders["table"] == "orders"
    order_cols = {c["name"]: c["type"] for c in orders["columns"]}  # type: ignore[index]
    assert order_cols["order_id"] == "BIGSERIAL"


def test_postgres_adapter_fail_closed_without_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch the name bound in ddl.py (from-import), not only _extra's attribute.
    import envassure.postgres.ddl as ddl_mod

    def _missing() -> Any:
        raise ImportError(POSTGRES_IMPORT_ERROR)

    monkeypatch.setattr(ddl_mod, "require_postgres_extra", _missing)
    with pytest.raises(ImportError, match=r"envassure\[postgres\]"):
        PostgresDDLAdapter()


def test_postgres_adapter_parses_when_extra_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.postgres.ddl as ddl_mod

    monkeypatch.setattr(ddl_mod, "require_postgres_extra", lambda: object())
    adapter = PostgresDDLAdapter()
    facts = adapter.parse(PG_SQL)
    predicates = {(f.subject.id, f.predicate) for f in facts}
    assert ("app.accounts", "is_aggregate") in predicates
    assert ("app.accounts", "schema_name") in predicates
    assert ("app.accounts.id", "column_type") in predicates


def test_import_postgres_kind_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.postgres.ddl as ddl_mod

    monkeypatch.setattr(
        ddl_mod,
        "require_postgres_extra",
        lambda: (_ for _ in ()).throw(ImportError(POSTGRES_IMPORT_ERROR)),
    )
    facts, report = import_source_report("postgres", PG_SQL)
    assert facts == []
    assert report.has_errors()
    codes = {d.code for d in report.diagnostics}
    assert "EAC1004" in codes
    assert "EAC9003" in codes


def test_postgres_connector_fail_closed_and_stub_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.postgres.connector as conn_mod

    monkeypatch.setattr(conn_mod, "require_postgres_extra", lambda: object())

    with pytest.raises(PermissionError, match="allow_live"):
        conn_mod.PostgresReferenceConnector(dsn="postgresql://localhost/db")

    cursor = MagicMock()
    cursor.fetchone.return_value = {"probe_id": "p1", "action_id": "act"}
    connection = MagicMock()
    connection.cursor.return_value = cursor

    connector = conn_mod.PostgresReferenceConnector(
        connection_factory=lambda: connection,
        allow_live=False,
    )
    connector.reset(seed=7)
    outcome = connector.execute("p1", "act", {"x": 1})
    assert outcome.success is True
    assert outcome.observation["probe_id"] == "p1"
    assert outcome.state["seed"] == 7
    connector.close()


def test_get_adapter_postgres_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.postgres.ddl as ddl_mod

    monkeypatch.setattr(ddl_mod, "require_postgres_extra", lambda: object())
    adapter = get_adapter("postgresql")
    assert adapter.kind == "postgres"


def test_stub_provider_always_available() -> None:
    provider = get_provider("stub", model_id="test-stub")
    proposal = provider.complete(
        "hello",
        subject="s",
        predicate="p",
        value={"ok": True},
    )
    assert proposal.authoritative is False
    assert proposal.origin == "model_proposal"
    assert proposal.prompt_digest
    assert proposal.isolation.get("prompt_injection_isolation") is True


def test_http_provider_requires_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.model_assisted.providers as prov

    def _missing() -> Any:
        raise ImportError(MODEL_ASSISTED_IMPORT_ERROR)

    monkeypatch.setattr(prov, "require_model_assisted_extra", _missing)
    with pytest.raises(ImportError, match=r"envassure\[model-assisted\]"):
        get_provider("http", base_url="http://127.0.0.1:9", enabled=True)


def test_http_provider_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.model_assisted.http as http_mod

    monkeypatch.setattr(http_mod, "require_model_assisted_extra", lambda: object())
    with pytest.raises(PermissionError, match="disabled"):
        http_mod.HttpProposalProvider(base_url="http://127.0.0.1:9", enabled=False)


def test_http_provider_opt_in_with_mock_client(monkeypatch: pytest.MonkeyPatch) -> None:
    import envassure.model_assisted.http as http_mod

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "subject": "acct",
                "predicate": "suggests",
                "value": {"limit": 10},
                "summary": "mocked",
            }

    class _Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> _Client:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def post(self, url: str, headers: dict[str, str], content: str) -> _Resp:
            assert "proposals" in url
            return _Resp()

    class _Httpx:
        Client = _Client

    monkeypatch.setattr(http_mod, "require_model_assisted_extra", lambda: _Httpx())
    provider = http_mod.HttpProposalProvider(
        base_url="http://127.0.0.1:8765",
        enabled=True,
        model_id="mock-http",
    )
    proposal = provider.complete("prompt text", subject="acct", predicate="suggests")
    assert proposal.authoritative is False
    assert proposal.authority == "model_proposal"
    assert proposal.isolation.get("taint") == "model_proposal"
    assert proposal.value == {"limit": 10}
    assert proposal.output_digest not in {"", "none"}


def test_provider_entry_points_include_stub() -> None:
    names = list_provider_entry_points()
    # Entry points appear after editable install; tolerate empty in bare path runs.
    assert isinstance(names, list)
    if names:
        assert "stub" in names


def test_doctor_lists_postgres_and_model_assisted_extras() -> None:
    result = run_doctor(network=False)
    names = {c.name for c in result.checks}
    assert "extra:postgres" in names
    assert "extra:model-assisted" in names


def test_require_model_assisted_extra_message(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def _guard(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "httpx" or name.startswith("httpx."):
            raise ImportError("no httpx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _guard)
    with pytest.raises(ImportError, match=r"envassure\[model-assisted\]"):
        require_model_assisted_extra()
