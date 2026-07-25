"""Lazy gate for the ``[postgres]`` optional extra."""

from __future__ import annotations

from typing import Any

POSTGRES_IMPORT_ERROR = (
    "psycopg is required for Postgres features. "
    "Install with: pip install 'envassure[postgres]'"
)


def require_postgres_extra() -> Any:
    """Import ``psycopg`` or raise a fail-closed ``ImportError``."""
    try:
        import psycopg
    except ImportError as exc:
        raise ImportError(POSTGRES_IMPORT_ERROR) from exc
    return psycopg
