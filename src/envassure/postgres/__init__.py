"""Postgres optional extra — DDL dialect and reference connector.

Install with ``pip install 'envassure[postgres]'``. Live database access is
opt-in and never required for the default test suite.
"""

from __future__ import annotations

from envassure.postgres._extra import POSTGRES_IMPORT_ERROR, require_postgres_extra
from envassure.postgres.connector import PostgresReferenceConnector
from envassure.postgres.ddl import PostgresDDLAdapter, parse_postgres_ddl

__all__ = [
    "POSTGRES_IMPORT_ERROR",
    "PostgresDDLAdapter",
    "PostgresReferenceConnector",
    "parse_postgres_ddl",
    "require_postgres_extra",
]
