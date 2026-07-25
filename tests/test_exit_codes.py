"""Exit code documentation consistency."""

from __future__ import annotations

from envassure.diagnostics.exit_codes import EXIT_CODE_DOCS, ExitCode


def test_every_exit_code_documented() -> None:
    for code in ExitCode:
        assert code in EXIT_CODE_DOCS
        assert EXIT_CODE_DOCS[code].strip()
