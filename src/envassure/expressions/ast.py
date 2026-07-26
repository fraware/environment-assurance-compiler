"""Expression abstract syntax tree nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeAlias
from typing import Literal as TypingLiteral

PathRoot = TypingLiteral["state", "actor", "payload", "context"]


@dataclass(frozen=True, slots=True)
class Literal:
    value: Any


@dataclass(frozen=True, slots=True)
class PathRef:
    """Dotted path rooted at state / actor / payload / context."""

    root: PathRoot
    parts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnaryOp:
    op: TypingLiteral["not", "neg", "pos"]
    operand: Expr


@dataclass(frozen=True, slots=True)
class BinaryOp:
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True, slots=True)
class Conditional:
    test: Expr
    then_branch: Expr
    else_branch: Expr


@dataclass(frozen=True, slots=True)
class Membership:
    """``item in collection`` / ``collection contains item``."""

    item: Expr
    collection: Expr
    inverted: bool = False


@dataclass(frozen=True, slots=True)
class CallExpr:
    name: str
    args: tuple[Expr, ...] = ()


@dataclass(frozen=True, slots=True)
class CollectionPred:
    """Bounded ``all`` / ``any`` over a collection (max *bound* elements)."""

    kind: TypingLiteral["all", "any"]
    var: str
    collection: Expr
    body: Expr
    bound: int = 64


Expr: TypeAlias = (
    Literal | PathRef | UnaryOp | BinaryOp | Conditional | Membership | CallExpr | CollectionPred
)
