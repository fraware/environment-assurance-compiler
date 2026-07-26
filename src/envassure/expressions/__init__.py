"""Typed expression AST, parser, type checker, and evaluator (EAC-R03)."""

from __future__ import annotations

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
from envassure.expressions.diagnostics import ExpressionDiagnostic, ExpressionError
from envassure.expressions.evaluate import EvalContext, evaluate, evaluate_bool
from envassure.expressions.parser import parse_expression, parse_structured
from envassure.expressions.types import ExprType, infer_type
from envassure.expressions.validate import validate_expression

__all__ = [
    "BinaryOp",
    "CallExpr",
    "CollectionPred",
    "Conditional",
    "EvalContext",
    "Expr",
    "ExprType",
    "ExpressionDiagnostic",
    "ExpressionError",
    "Literal",
    "Membership",
    "PathRef",
    "UnaryOp",
    "evaluate",
    "evaluate_bool",
    "infer_type",
    "parse_expression",
    "parse_structured",
    "validate_expression",
]
