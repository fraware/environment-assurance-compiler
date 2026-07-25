"""Safe evaluation of typed expression ASTs."""

from __future__ import annotations

from dataclasses import dataclass, field
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
from envassure.expressions.types import ALLOWLISTED_FUNCTIONS


@dataclass
class EvalContext:
    """Evaluation bindings for expression paths and collection predicates."""

    state: dict[str, Any] = field(default_factory=dict)
    actor: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    locals_: dict[str, Any] = field(default_factory=dict)


def evaluate(expr: Expr, ctx: EvalContext) -> Any:
    """Evaluate *expr* against *ctx*; never silently coerces errors to False."""
    if isinstance(expr, Literal):
        return expr.value
    if isinstance(expr, PathRef):
        return _resolve_path(expr, ctx)
    if isinstance(expr, UnaryOp):
        value = evaluate(expr.operand, ctx)
        if expr.op == "not":
            return not bool(value)
        if expr.op == "neg":
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ExpressionError("unary - requires a number", code="EAC_EXPR_TYPE")
            return -value
        if expr.op == "pos":
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ExpressionError("unary + requires a number", code="EAC_EXPR_TYPE")
            return +value
        raise ExpressionError(f"unsupported unary op {expr.op!r}", code="EAC_EXPR_UNSUPPORTED_OP")
    if isinstance(expr, BinaryOp):
        return _eval_binary(expr, ctx)
    if isinstance(expr, Conditional):
        if evaluate_bool(expr.test, ctx):
            return evaluate(expr.then_branch, ctx)
        return evaluate(expr.else_branch, ctx)
    if isinstance(expr, Membership):
        item = evaluate(expr.item, ctx)
        collection = evaluate(expr.collection, ctx)
        if isinstance(collection, dict):
            found = item in collection
        elif isinstance(collection, list | tuple | set | str):
            found = item in collection
        else:
            raise ExpressionError(
                f"membership requires a collection, got {type(collection).__name__}",
                code="EAC_EXPR_TYPE",
            )
        return (not found) if expr.inverted else found
    if isinstance(expr, CallExpr):
        return _eval_call(expr, ctx)
    if isinstance(expr, CollectionPred):
        return _eval_collection_pred(expr, ctx)
    raise ExpressionError(
        f"unsupported expression node {type(expr).__name__}",
        code="EAC_EXPR_UNSUPPORTED",
    )


def evaluate_bool(expr: Expr, ctx: EvalContext) -> bool:
    """Evaluate *expr* and require a Boolean (or truthy for path-only legacy)."""
    value = evaluate(expr, ctx)
    if isinstance(value, bool):
        return value
    # Paths used as bare constraints remain truthy-checks (legacy packs).
    if isinstance(expr, PathRef):
        return bool(value)
    if value is None:
        return False
    if isinstance(value, int | float | str | list | dict):
        return bool(value)
    raise ExpressionError(
        f"constraint did not evaluate to a boolean: {value!r}",
        code="EAC_EXPR_TYPE",
    )


def _resolve_path(path: PathRef, ctx: EvalContext) -> Any:
    # Collection-pred locals shadow path roots when the first segment matches.
    if path.parts and path.parts[0] in ctx.locals_:
        cur: Any = ctx.locals_[path.parts[0]]
        for part in path.parts[1:]:
            cur = _index(cur, part)
        return cur

    roots = {
        "state": ctx.state,
        "actor": ctx.actor,
        "payload": ctx.payload,
        "context": ctx.context,
    }
    cur = roots[path.root]
    for part in path.parts:
        cur = _index(cur, part)
    return cur


def _index(cur: Any, part: str) -> Any:
    if cur is None:
        return None
    if isinstance(cur, dict):
        return cur.get(part)
    if hasattr(cur, part):
        return getattr(cur, part)
    raise ExpressionError(
        f"cannot resolve path segment {part!r} on {type(cur).__name__}",
        code="EAC_EXPR_PATH",
    )


def _eval_binary(expr: BinaryOp, ctx: EvalContext) -> Any:
    op = expr.op
    if op == "and":
        return evaluate_bool(expr.left, ctx) and evaluate_bool(expr.right, ctx)
    if op == "or":
        return evaluate_bool(expr.left, ctx) or evaluate_bool(expr.right, ctx)

    left = evaluate(expr.left, ctx)
    right = evaluate(expr.right, ctx)

    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    if op in {"<", "<=", ">", ">="}:
        if not _both_numbers(left, right):
            raise ExpressionError(
                f"ordered comparison requires numbers, got {left!r} and {right!r}",
                code="EAC_EXPR_TYPE",
            )
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        return left >= right
    if op in {"+", "-", "*", "/", "//", "%"}:
        if op == "+" and isinstance(left, str) and isinstance(right, str):
            return left + right
        if not _both_numbers(left, right):
            raise ExpressionError(
                f"arithmetic requires numbers, got {left!r} and {right!r}",
                code="EAC_EXPR_TYPE",
            )
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right
        if op == "//":
            return left // right
        return left % right
    raise ExpressionError(f"unsupported binary op {op!r}", code="EAC_EXPR_UNSUPPORTED_OP")


def _both_numbers(left: Any, right: Any) -> bool:
    return (
        isinstance(left, int | float)
        and isinstance(right, int | float)
        and not isinstance(left, bool)
        and not isinstance(right, bool)
    )


def _eval_call(expr: CallExpr, ctx: EvalContext) -> Any:
    if expr.name not in ALLOWLISTED_FUNCTIONS:
        raise ExpressionError(
            f"function {expr.name!r} is not allowlisted",
            code="EAC_EXPR_UNKNOWN_FUNCTION",
        )
    args = [evaluate(a, ctx) for a in expr.args]
    name = expr.name
    try:
        if name == "len":
            return len(args[0])  # type: ignore[arg-type]
        if name == "abs":
            return abs(args[0])
        if name == "min":
            return min(args) if len(args) > 1 else min(args[0])  # type: ignore[call-overload]
        if name == "max":
            return max(args) if len(args) > 1 else max(args[0])  # type: ignore[call-overload]
        if name == "str":
            return str(args[0])
        if name == "bool":
            return bool(args[0])
        if name == "int":
            return int(args[0])
        if name == "float":
            return float(args[0])
        if name == "keys":
            return list(args[0].keys())  # type: ignore[union-attr]
        if name == "values":
            return list(args[0].values())  # type: ignore[union-attr]
        if name == "lower":
            return str(args[0]).lower()
        if name == "upper":
            return str(args[0]).upper()
    except (TypeError, ValueError, AttributeError, IndexError) as exc:
        raise ExpressionError(
            f"call {name} failed: {exc}",
            code="EAC_EXPR_CALL",
        ) from exc
    raise ExpressionError(f"unhandled allowlisted function {name!r}", code="EAC_EXPR_CALL")


def _eval_collection_pred(expr: CollectionPred, ctx: EvalContext) -> bool:
    collection = evaluate(expr.collection, ctx)
    if isinstance(collection, dict):
        items = list(collection.values())
    elif isinstance(collection, list | tuple):
        items = list(collection)
    elif isinstance(collection, set):
        items = list(collection)
    else:
        raise ExpressionError(
            f"{expr.kind} requires a collection, got {type(collection).__name__}",
            code="EAC_EXPR_TYPE",
        )
    if len(items) > expr.bound:
        raise ExpressionError(
            f"{expr.kind} collection exceeds bound {expr.bound}",
            code="EAC_EXPR_BOUND",
        )
    saved = dict(ctx.locals_)
    try:
        if expr.kind == "all":
            for item in items:
                ctx.locals_[expr.var] = item
                # Also allow state.<var> style via locals shadow in path resolver
                if not evaluate_bool(expr.body, ctx):
                    return False
            return True
        for item in items:
            ctx.locals_[expr.var] = item
            if evaluate_bool(expr.body, ctx):
                return True
        return False
    finally:
        ctx.locals_.clear()
        ctx.locals_.update(saved)
