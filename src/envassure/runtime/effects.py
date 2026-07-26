"""Effect expression helpers for intended_effects and initial generators."""

from __future__ import annotations

from typing import Any

from envassure.expressions.diagnostics import ExpressionError
from envassure.expressions.evaluate import EvalContext, evaluate, evaluate_bool
from envassure.expressions.parser import (
    coerce_literal,
    parse_effect,
    parse_expression,
    parse_structured,
)
from envassure.expressions.types import infer_type
from envassure.expressions.validate import validate_expression
from envassure.ir.primitives import ConstraintExpr


def apply_effect(
    state: dict[str, Any],
    expression: str,
    *,
    actor: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply one intended_effect string; return the write map for the event.

    Raises ``ValueError`` / ``ExpressionError`` on unsupported semantics (fail closed).
    """
    try:
        name, op, rhs = parse_effect(expression)
        infer_type(rhs)
        ctx = EvalContext(
            state=state,
            actor=actor or {},
            payload=payload or {},
            context=context or {},
        )
        value = evaluate(rhs, ctx)
        if op == "+=":
            current = state.get(name, 0)
            if not isinstance(current, int | float) or isinstance(current, bool):
                raise ValueError(f"cannot apply increment {expression!r} to {current!r}")
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"increment delta must be numeric, got {value!r}")
            new_value: Any = current + value
        elif op == "-=":
            current = state.get(name, 0)
            if not isinstance(current, int | float) or isinstance(current, bool):
                raise ValueError(f"cannot apply decrement {expression!r} to {current!r}")
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"decrement delta must be numeric, got {value!r}")
            new_value = current - value
        else:
            new_value = value
        state[name] = new_value
        return {name: new_value}
    except ExpressionError as exc:
        raise ValueError(str(exc)) from exc


def evaluate_constraint(
    expression: str | ConstraintExpr,
    *,
    state: dict[str, Any],
    actor: dict[str, Any],
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a constraint; unsupported forms raise (caller maps to unsupported_semantics).

    Never silently treats parse failures as False.
    """
    structured: dict[str, Any] | None = None
    text: str
    if isinstance(expression, ConstraintExpr):
        text = expression.expression
        structured = expression.structured
    else:
        text = expression

    try:
        if structured:
            expr, diags = validate_expression(structured=structured)
            if expr is None:
                raise ExpressionError(
                    diags[0].message if diags else "invalid structured expression",
                    code="EAC_EXPR_UNSUPPORTED",
                    expression=text,
                )
        else:
            expr = parse_expression(text)
            infer_type(expr)
        ctx = EvalContext(
            state=state,
            actor=actor,
            payload=payload or {},
            context=context or {},
        )
        return evaluate_bool(expr, ctx)
    except ExpressionError:
        raise
    except ValueError as exc:
        raise ExpressionError(str(exc), code="EAC_EXPR_UNSUPPORTED", expression=text) from exc


__all__ = [
    "apply_effect",
    "coerce_literal",
    "evaluate_constraint",
    "parse_expression",
    "parse_structured",
]
