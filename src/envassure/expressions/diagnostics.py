"""Expression diagnostics and errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ExpressionDiagnostic:
    code: str
    message: str
    expression: str | None = None
    details: dict[str, Any] | None = None


class ExpressionError(ValueError):
    """Raised when an expression cannot be parsed, typed, or evaluated safely."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "EAC_EXPR",
        expression: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.expression = expression
        self.details = details or {}

    def to_diagnostic(self) -> ExpressionDiagnostic:
        return ExpressionDiagnostic(
            code=self.code,
            message=str(self),
            expression=self.expression,
            details=self.details or None,
        )
