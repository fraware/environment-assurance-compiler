"""Fail-closed stubs for unimplemented CLI commands."""

from __future__ import annotations

from collections.abc import Callable

import typer

from envassure.cli.output import fail_unimplemented


def make_stub(command_name: str) -> Callable[..., None]:
    def stub(
        as_json: bool = typer.Option(
            False,
            "--json",
            help="Emit machine-readable JSON.",
        ),
    ) -> None:
        fail_unimplemented(command_name, as_json=as_json)

    stub.__name__ = command_name.replace("-", "_")
    stub.__doc__ = f"Not implemented yet (fail-closed). Reserved command `{command_name}`."
    return stub
