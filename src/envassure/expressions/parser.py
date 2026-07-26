"""Recursive-descent parser for EnvAssure constraint / effect expressions."""

from __future__ import annotations

import ast as py_ast
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
    PathRoot,
    UnaryOp,
)
from envassure.expressions.diagnostics import ExpressionError

_ROOTS: frozenset[str] = frozenset({"state", "actor", "payload", "context"})
_KEYWORDS: frozenset[str] = frozenset(
    {
        "and",
        "or",
        "not",
        "in",
        "contains",
        "true",
        "false",
        "null",
        "none",
        "if",
        "then",
        "else",
        "all",
        "any",
    }
)


class _Tok:
    __slots__ = ("kind", "value")

    def __init__(self, kind: str, value: str) -> None:
        self.kind = kind
        self.value = value


def _tokenize(text: str) -> list[_Tok]:
    tokens: list[_Tok] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        # Multi-char operators
        if (
            text.startswith("==", i)
            or text.startswith("!=", i)
            or text.startswith("<=", i)
            or text.startswith(">=", i)
            or text.startswith("//", i)
        ):
            tokens.append(_Tok("op", text[i : i + 2]))
            i += 2
            continue
        if ch in "+-*/%<>=!":
            tokens.append(_Tok("op", ch))
            i += 1
            continue
        if ch in "(),[]{}:.,":
            tokens.append(_Tok(ch, ch))
            i += 1
            continue
        if ch in "'\"":
            quote = ch
            j = i + 1
            buf: list[str] = []
            while j < n:
                c = text[j]
                if c == "\\" and j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                if c == quote:
                    tokens.append(_Tok("string", "".join(buf)))
                    j += 1
                    break
                buf.append(c)
                j += 1
            else:
                raise ExpressionError(
                    "unterminated string literal",
                    code="EAC_EXPR_PARSE",
                    expression=text,
                )
            i = j
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and text[i + 1].isdigit()):
            j = i
            while j < n and (text[j].isdigit() or text[j] == "."):
                j += 1
            tokens.append(_Tok("number", text[i:j]))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            word = text[i:j]
            lower = word.lower()
            if lower in _KEYWORDS:
                tokens.append(_Tok("kw", lower))
            else:
                tokens.append(_Tok("id", word))
            i = j
            continue
        raise ExpressionError(
            f"unexpected character {ch!r}",
            code="EAC_EXPR_PARSE",
            expression=text,
        )
    tokens.append(_Tok("eof", ""))
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _tokenize(text)
        self.pos = 0

    def _cur(self) -> _Tok:
        return self.tokens[self.pos]

    def _advance(self) -> _Tok:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _match(self, *kinds: str) -> _Tok | None:
        if self._cur().kind in kinds or self._cur().value in kinds:
            return self._advance()
        return None

    def _expect(self, *kinds: str) -> _Tok:
        tok = self._match(*kinds)
        if tok is None:
            raise ExpressionError(
                f"expected {kinds!r}, got {self._cur().kind}:{self._cur().value!r}",
                code="EAC_EXPR_PARSE",
                expression=self.text,
            )
        return tok

    def parse(self) -> Expr:
        expr = self.parse_or()
        if self._cur().kind != "eof":
            raise ExpressionError(
                f"trailing tokens near {self._cur().value!r}",
                code="EAC_EXPR_PARSE",
                expression=self.text,
            )
        return expr

    def parse_or(self) -> Expr:
        left = self.parse_and()
        while self._match("or"):
            right = self.parse_and()
            left = BinaryOp("or", left, right)
        return left

    def parse_and(self) -> Expr:
        left = self.parse_not()
        while self._match("and"):
            right = self.parse_not()
            left = BinaryOp("and", left, right)
        return left

    def parse_not(self) -> Expr:
        if self._match("not"):
            return UnaryOp("not", self.parse_not())
        return self.parse_comparison()

    def parse_comparison(self) -> Expr:
        left = self.parse_add()
        # membership: X in Y / X contains Y
        if self._match("in"):
            return Membership(item=left, collection=self.parse_add())
        if self._match("contains"):
            return Membership(item=self.parse_add(), collection=left)
        tok = self._cur()
        if tok.kind == "op" and tok.value in {"==", "!=", "<", "<=", ">", ">="}:
            op = self._advance().value
            right = self.parse_add()
            return BinaryOp(op, left, right)
        return left

    def parse_add(self) -> Expr:
        left = self.parse_mul()
        while self._cur().kind == "op" and self._cur().value in {"+", "-"}:
            op = self._advance().value
            right = self.parse_mul()
            left = BinaryOp(op, left, right)
        return left

    def parse_mul(self) -> Expr:
        left = self.parse_unary()
        while self._cur().kind == "op" and self._cur().value in {"*", "/", "//", "%"}:
            op = self._advance().value
            right = self.parse_unary()
            left = BinaryOp(op, left, right)
        return left

    def parse_unary(self) -> Expr:
        if self._cur().kind == "op" and self._cur().value == "-":
            self._advance()
            return UnaryOp("neg", self.parse_unary())
        if self._cur().kind == "op" and self._cur().value == "+":
            self._advance()
            return UnaryOp("pos", self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        tok = self._cur()
        # Conditional: if C then A else B
        if self._match("if"):
            test = self.parse_or()
            self._expect("then")
            then_b = self.parse_or()
            self._expect("else")
            else_b = self.parse_or()
            return Conditional(test, then_b, else_b)

        # Collection predicates: all x in coll: body / any x in coll: body
        if tok.kind == "kw" and tok.value in {"all", "any"}:
            kind_raw = self._advance().value
            if kind_raw not in {"all", "any"}:
                raise ExpressionError(
                    f"expected all/any, got {kind_raw!r}",
                    code="EAC_EXPR_SYNTAX",
                )
            var_tok = self._expect("id")
            self._expect("in")
            collection = self.parse_or()
            self._expect(":")
            body = self.parse_or()
            return CollectionPred(
                kind="all" if kind_raw == "all" else "any",
                var=var_tok.value,
                collection=collection,
                body=body,
            )

        if self._match("("):
            inner = self.parse_or()
            self._expect(")")
            return inner

        if tok.kind == "string":
            self._advance()
            return Literal(tok.value)

        if tok.kind == "number":
            self._advance()
            raw = tok.value
            if "." in raw:
                return Literal(float(raw))
            return Literal(int(raw))

        if tok.kind == "kw":
            if tok.value == "true":
                self._advance()
                return Literal(True)
            if tok.value == "false":
                self._advance()
                return Literal(False)
            if tok.value in {"null", "none"}:
                self._advance()
                return Literal(None)

        if tok.kind == "id":
            return self._parse_atom_path_or_call()

        raise ExpressionError(
            f"unexpected token {tok.kind}:{tok.value!r}",
            code="EAC_EXPR_PARSE",
            expression=self.text,
        )

    def _parse_atom_path_or_call(self) -> Expr:
        tok = self._expect("id")
        name = tok.value
        if self._match("("):
            args: list[Expr] = []
            if self._cur().kind != ")":
                args.append(self.parse_or())
                while self._match(","):
                    args.append(self.parse_or())
            self._expect(")")
            return CallExpr(name, tuple(args))

        # Path: root.a.b or bare identifier → state.<name> by default
        parts: list[str] = []
        root: PathRoot
        if name in _ROOTS:
            root = name  # type: ignore[assignment]
        else:
            root = "state"
            parts.append(name)
        while self._match("."):
            nxt = self._expect("id")
            parts.append(nxt.value)
        return PathRef(root=root, parts=tuple(parts))


def parse_expression(text: str) -> Expr:
    """Parse a constraint/effect RHS expression string into an AST."""
    stripped = text.strip()
    if not stripped:
        raise ExpressionError(
            "empty expression",
            code="EAC_EXPR_EMPTY",
            expression=text,
        )
    try:
        return _Parser(stripped).parse()
    except ExpressionError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise ExpressionError(
            f"failed to parse expression: {exc}",
            code="EAC_EXPR_PARSE",
            expression=text,
        ) from exc


def parse_effect(expression: str) -> tuple[str, str, Expr]:
    """Parse an intended_effect assignment / increment / decrement.

    Returns ``(target_name, op, rhs_expr)`` where *op* is ``=``, ``+=``, or ``-=``.
    """
    text = expression.strip()
    for op in ("+=", "-=", "="):
        if op in text:
            left, _, right = text.partition(op)
            name = left.strip()
            # Allow dotted targets later; for now top-level state ids.
            if (not name or not all(c.isalnum() or c == "_" for c in name)) and (
                not name.replace(".", "").replace("_", "").isalnum()
            ):
                continue
            # Only simple identifiers for write targets (state keys).
            if "." in name:
                raise ExpressionError(
                    f"nested effect targets are unsupported: {name!r}",
                    code="EAC_EXPR_UNSUPPORTED",
                    expression=expression,
                )
            if not name.isidentifier():
                continue
            return name, op, parse_expression(right.strip())
    raise ExpressionError(
        f"unsupported intended_effect expression: {expression!r}",
        code="EAC_EXPR_UNSUPPORTED",
        expression=expression,
    )


def parse_structured(structured: dict[str, Any]) -> Expr:
    """Compile ``ConstraintExpr.structured`` maps into an AST (fail-closed)."""
    if not structured:
        raise ExpressionError(
            "empty structured expression",
            code="EAC_EXPR_EMPTY",
        )

    if "lit" in structured or "literal" in structured:
        return Literal(structured.get("lit", structured.get("literal")))

    if "path" in structured:
        return _path_from_string(str(structured["path"]))

    if "eq" in structured or "equals" in structured:
        pair = structured.get("eq") or structured.get("equals")
        left, right = _pair(pair, structured, "left", "right")
        return BinaryOp("==", _node(left), _node(right))

    if "neq" in structured or "not_equals" in structured:
        pair = structured.get("neq") or structured.get("not_equals")
        if "not_equals" in structured and not isinstance(pair, list | tuple):
            # Compact form used by tasks: {"not_equals": value} needs a path.
            raise ExpressionError(
                "not_equals structured form requires [left, right] or left/right keys",
                code="EAC_EXPR_UNSUPPORTED",
            )
        left, right = _pair(pair, structured, "left", "right")
        return BinaryOp("!=", _node(left), _node(right))

    for op, key in (
        (">=", "gte"),
        (">=", "ge"),
        ("<=", "lte"),
        ("<=", "le"),
        (">", "gt"),
        ("<", "lt"),
    ):
        if key in structured:
            left, right = _pair(structured[key], structured, "left", "right")
            return BinaryOp(op, _node(left), _node(right))

    if "and" in structured:
        items = structured["and"]
        if not isinstance(items, list) or not items:
            raise ExpressionError("and requires a non-empty list", code="EAC_EXPR_PARSE")
        acc = _node(items[0])
        for item in items[1:]:
            acc = BinaryOp("and", acc, _node(item))
        return acc

    if "or" in structured:
        items = structured["or"]
        if not isinstance(items, list) or not items:
            raise ExpressionError("or requires a non-empty list", code="EAC_EXPR_PARSE")
        acc = _node(items[0])
        for item in items[1:]:
            acc = BinaryOp("or", acc, _node(item))
        return acc

    if "not" in structured:
        return UnaryOp("not", _node(structured["not"]))

    if "in" in structured:
        pair = structured["in"]
        if isinstance(pair, list | tuple) and len(pair) == 2:
            return Membership(item=_node(pair[0]), collection=_node(pair[1]))
        raise ExpressionError("in requires [item, collection]", code="EAC_EXPR_PARSE")

    if "contains" in structured:
        pair = structured["contains"]
        if isinstance(pair, list | tuple) and len(pair) == 2:
            return Membership(item=_node(pair[1]), collection=_node(pair[0]))
        raise ExpressionError(
            "contains requires [collection, item]",
            code="EAC_EXPR_PARSE",
        )

    if "if" in structured:
        block = structured["if"]
        if not isinstance(block, dict):
            raise ExpressionError("if requires {test, then, else}", code="EAC_EXPR_PARSE")
        return Conditional(
            _node(block["test"]),
            _node(block["then"]),
            _node(block["else"]),
        )

    if "call" in structured:
        block = structured["call"]
        if not isinstance(block, dict) or "name" not in block:
            raise ExpressionError("call requires {name, args?}", code="EAC_EXPR_PARSE")
        args_raw = block.get("args") or []
        if not isinstance(args_raw, list):
            raise ExpressionError("call.args must be a list", code="EAC_EXPR_PARSE")
        return CallExpr(str(block["name"]), tuple(_node(a) for a in args_raw))

    if "all" in structured or "any" in structured:
        kind = "all" if "all" in structured else "any"
        block = structured[kind]
        if not isinstance(block, dict):
            raise ExpressionError(f"{kind} requires object body", code="EAC_EXPR_PARSE")
        return CollectionPred(
            kind=kind,  # type: ignore[arg-type]
            var=str(block["var"]),
            collection=_node(block["collection"]),
            body=_node(block["body"]),
            bound=int(block.get("bound", 64)),
        )

    raise ExpressionError(
        f"unsupported structured expression keys: {sorted(structured)}",
        code="EAC_EXPR_UNSUPPORTED",
    )


def _node(value: Any) -> Expr:
    if isinstance(value, dict):
        return parse_structured(value)
    if isinstance(value, str):
        # Path-like or literal string? Prefer path when it looks like one.
        if value.startswith(("state.", "actor.", "payload.", "context.")) or (
            value.isidentifier() and value not in {"true", "false", "null", "none"}
        ):
            try:
                return parse_expression(value)
            except ExpressionError:
                return Literal(value)
        return parse_expression(value) if _looks_like_expr(value) else Literal(value)
    return Literal(value)


def _looks_like_expr(value: str) -> bool:
    for marker in ("==", "!=", ">=", "<=", ">", "<", " and ", " or ", " in ", " contains "):
        if marker in value:
            return True
    return False


def _pair(
    pair: Any,
    structured: dict[str, Any],
    left_key: str,
    right_key: str,
) -> tuple[Any, Any]:
    if isinstance(pair, list | tuple) and len(pair) == 2:
        return pair[0], pair[1]
    if left_key in structured and right_key in structured:
        return structured[left_key], structured[right_key]
    raise ExpressionError(
        f"expected pair list or {left_key}/{right_key} keys",
        code="EAC_EXPR_PARSE",
    )


def _path_from_string(path: str) -> PathRef:
    parts = path.split(".")
    if parts[0] in _ROOTS:
        return PathRef(root=parts[0], parts=tuple(parts[1:]))  # type: ignore[arg-type]
    return PathRef(root="state", parts=tuple(parts))


def coerce_literal(raw: str) -> Any:
    """Parse a simple literal used in IR generators (legacy helper)."""
    text = raw.strip()
    if not text:
        return None
    try:
        return py_ast.literal_eval(text)
    except (SyntaxError, ValueError):
        pass
    lower = text.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in {"null", "none"}:
        return None
    return text
