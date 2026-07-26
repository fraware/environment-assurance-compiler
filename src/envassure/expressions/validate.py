"""Expression validation / type-checking entrypoints."""

from __future__ import annotations

from typing import Any

from envassure.expressions.ast import Expr
from envassure.expressions.diagnostics import ExpressionDiagnostic, ExpressionError
from envassure.expressions.parser import parse_expression, parse_structured
from envassure.expressions.types import infer_type


def validate_expression(
    expression: str | None = None,
    *,
    structured: dict[str, Any] | None = None,
) -> tuple[Expr | None, list[ExpressionDiagnostic]]:
    """Parse and type-check an expression; return AST or diagnostics (fail-closed)."""
    diagnostics: list[ExpressionDiagnostic] = []
    try:
        if structured:
            expr = parse_structured(structured)
        elif expression is not None:
            expr = parse_expression(expression)
        else:
            raise ExpressionError("no expression provided", code="EAC_EXPR_EMPTY")
        infer_type(expr)
        return expr, diagnostics
    except ExpressionError as exc:
        diagnostics.append(exc.to_diagnostic())
        return None, diagnostics
