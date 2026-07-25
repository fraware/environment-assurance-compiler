"""Stable process exit codes for the `eac` CLI."""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Documented exit codes. See docs/reference/exit-codes.md."""

    SUCCESS = 0
    ERROR = 1
    USAGE = 2
    UNIMPLEMENTED = 3
    WORKSPACE = 4
    DOCTOR = 5
    INTERNAL = 99


EXIT_CODE_DOCS: dict[ExitCode, str] = {
    ExitCode.SUCCESS: "Command completed successfully with no blocking diagnostics.",
    ExitCode.ERROR: "Blocking diagnostics or general command failure.",
    ExitCode.USAGE: "Invalid CLI usage or argument parsing failure.",
    ExitCode.UNIMPLEMENTED: "Command is registered but not yet implemented (fail-closed).",
    ExitCode.WORKSPACE: "Workspace missing, invalid, or lock inconsistency.",
    ExitCode.DOCTOR: "Doctor checks failed.",
    ExitCode.INTERNAL: "Unexpected internal error.",
}
