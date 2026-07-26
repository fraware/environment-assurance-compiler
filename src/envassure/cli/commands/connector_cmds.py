"""CLI: ``eac connector doctor``."""

from __future__ import annotations

from typing import Any

import typer

from envassure.cli.output import emit_report, emit_success
from envassure.diagnostics.exit_codes import ExitCode
from envassure.diagnostics.models import DiagnosticReport
from envassure.differential.http_connector import (
    HttpReferenceConnector,
    ReferenceSystemConnectorError,
)

connector_app = typer.Typer(
    name="connector",
    help="Reference-system connector health checks.",
    no_args_is_help=True,
)


@connector_app.command("doctor")
def connector_doctor(
    http_url: str = typer.Option(
        ...,
        "--http-url",
        help="Base URL of the reference service (loopback by default).",
    ),
    allow_network: bool = typer.Option(
        False,
        "--allow-network",
        help="Opt in to network (required for HTTP doctor).",
    ),
    allow_non_loopback: bool = typer.Option(
        False,
        "--allow-non-loopback",
        help="Permit non-loopback hosts (CI only).",
    ),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Evaluator token for privileged probes.",
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Check HTTP reference connector healthz + privileged state access."""
    try:
        connector = HttpReferenceConnector(
            http_url,
            allow_network=allow_network,
            allow_non_loopback=allow_non_loopback,
            privileged_token=token,
        )
        result: dict[str, Any] = connector.doctor()
    except (PermissionError, ReferenceSystemConnectorError) as exc:
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra={"error": str(exc)},
        )
        return
    if not result.get("ok"):
        emit_report(
            DiagnosticReport(),
            as_json=as_json,
            exit_code=ExitCode.ERROR,
            extra=result,
        )
        return
    emit_success(as_json=as_json, message="Connector doctor OK", extra=result)
