"""Expression type tags and inference (fail-closed)."""

from __future__ import annotations

from enum import Enum
from typing import Any

from envassure.expressions.ast import (
    BinaryOp,
    CallExpr,
    CollectionPred,
    Conditional,
    Expr,
    Literal,
    Membership,
    PathRef,
    UnaryOp,
)
from envassure.expressions.diagnostics import ExpressionError

# Pure allowlisted functions and their result types.
ALLOWLISTED_FUNCTIONS: dict[str, str] = {
    "len": "number",
    "abs": "number",
    "min": "number",
    "max": "number",
    "str": "string",
    "bool": "boolean",
    "int": "number",
    "float": "number",
    "keys": "list",
    "values": "list",
    "lower": "string",
    "upper": "string",
}


class ExprType(str, Enum):
    ANY = "any"
    NULL = "null"
    BOOLEAN = "boolean"
    NUMBER = "number"
    STRING = "string"
    LIST = "list"
    MAP = "map"
    UNKNOWN = "unknown"


_ARITH = frozenset({"+", "-", "*", "/", "//", "%"})
_CMP = frozenset({"==", "!=", "<", "<=", ">", ">="})
_LOGIC = frozenset({"and", "or"})


def type_of_value(value: Any) -> ExprType:
    if value is None:
        return ExprType.NULL
    if isinstance(value, bool):
        return ExprType.BOOLEAN
    if isinstance(value, int | float) and not isinstance(value, bool):
        return ExprType.NUMBER
    if isinstance(value, str):
        return ExprType.STRING
    if isinstance(value, list | tuple | set):
        return ExprType.LIST
    if isinstance(value, dict):
        return ExprType.MAP
    return ExprType.UNKNOWN


def infer_type(expr: Expr) -> ExprType:
    """Infer a coarse type; raises ExpressionError on unsupported forms."""
    if isinstance(expr, Literal):
        return type_of_value(expr.value)
    if isinstance(expr, PathRef):
        return ExprType.ANY
    if isinstance(expr, UnaryOp):
        if expr.op == "not":
            return ExprType.BOOLEAN
        return ExprType.NUMBER
    if isinstance(expr, BinaryOp):
        if expr.op in _LOGIC or expr.op in _CMP:
            return ExprType.BOOLEAN
        if expr.op in _ARITH:
            return ExprType.NUMBER
        if expr.op == "+":
            # Could be string concat; treat as any.
            return ExprType.ANY
        raise ExpressionError(
            f"unsupported binary operator {expr.op!r}",
            code="EAC_EXPR_UNSUPPORTED_OP",
        )
    if isinstance(expr, Conditional):
        then_t = infer_type(expr.then_branch)
        else_t = infer_type(expr.else_branch)
        if then_t == else_t:
            return then_t
        return ExprType.ANY
    if isinstance(expr, Membership):
        return ExprType.BOOLEAN
    if isinstance(expr, CallExpr):
        result = ALLOWLISTED_FUNCTIONS.get(expr.name)
        if result is None:
            raise ExpressionError(
                f"function {expr.name!r} is not allowlisted",
                code="EAC_EXPR_UNKNOWN_FUNCTION",
            )
        return ExprType(result) if result in ExprType._value2member_map_ else ExprType.ANY
    if isinstance(expr, CollectionPred):
        return ExprType.BOOLEAN
    raise ExpressionError(
        f"unsupported expression node {type(expr).__name__}",
        code="EAC_EXPR_UNSUPPORTED",
    )
