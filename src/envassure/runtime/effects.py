"""Effect expression helpers for intended_effects and initial generators."""

from __future__ import annotations

import ast
import re
from typing import Any

_INCREMENT = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\+=\s*(?P<value>.+?)\s*$")
_DECREMENT = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*-=\s*(?P<value>.+?)\s*$")
_ASSIGN = re.compile(r"^\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>.+?)\s*$")


def coerce_literal(raw: str) -> Any:
    """Parse a simple literal / identifier used in IR generators and effects."""
    text = raw.strip()
    if not text:
        return None
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        pass
    if text.lower() == "true":
        return True
    if text.lower() == "false":
        return False
    if text.lower() == "null" or text.lower() == "none":
        return None
    return text


def apply_effect(state: dict[str, Any], expression: str) -> dict[str, Any]:
    """Apply one intended_effect string; return the write map for the event."""
    writes: dict[str, Any] = {}
    m = _INCREMENT.match(expression)
    if m:
        name = m.group("name")
        delta = coerce_literal(m.group("value"))
        current = state.get(name, 0)
        if not isinstance(current, int | float) or not isinstance(delta, int | float):
            raise ValueError(f"cannot apply increment {expression!r} to {current!r}")
        new_value = current + delta
        state[name] = new_value
        writes[name] = new_value
        return writes
    m = _DECREMENT.match(expression)
    if m:
        name = m.group("name")
        delta = coerce_literal(m.group("value"))
        current = state.get(name, 0)
        if not isinstance(current, int | float) or not isinstance(delta, int | float):
            raise ValueError(f"cannot apply decrement {expression!r} to {current!r}")
        new_value = current - delta
        state[name] = new_value
        writes[name] = new_value
        return writes
    m = _ASSIGN.match(expression)
    if m:
        name = m.group("name")
        value = coerce_literal(m.group("value"))
        state[name] = value
        writes[name] = value
        return writes
    raise ValueError(f"unsupported intended_effect expression: {expression!r}")


def evaluate_constraint(expression: str, *, state: dict[str, Any], actor: dict[str, Any]) -> bool:
    """Evaluate a tiny subset of constraint expressions used in reference packs."""
    text = expression.strip()
    # Equality: name == value
    eq = re.match(
        r"^(?P<lhs>[A-Za-z_][A-Za-z0-9_\.]*)\s*==\s*(?P<rhs>.+)$",
        text,
    )
    if eq:
        lhs = _resolve_path(eq.group("lhs"), state=state, actor=actor)
        rhs = coerce_literal(eq.group("rhs"))
        return bool(lhs == rhs)
    # Inequality: name >= value / > / <= / <
    cmp_m = re.match(
        r"^(?P<lhs>[A-Za-z_][A-Za-z0-9_\.]*)\s*(?P<op>>=|<=|>|<)\s*(?P<rhs>.+)$",
        text,
    )
    if cmp_m:
        lhs = _resolve_path(cmp_m.group("lhs"), state=state, actor=actor)
        rhs = coerce_literal(cmp_m.group("rhs"))
        op = cmp_m.group("op")
        if not isinstance(lhs, int | float) or not isinstance(rhs, int | float):
            return False
        if op == ">=":
            return lhs >= rhs
        if op == "<=":
            return lhs <= rhs
        if op == ">":
            return lhs > rhs
        return lhs < rhs
    # Membership: actor.roles contains X
    contains = re.match(
        r"^(?P<lhs>[A-Za-z_][A-Za-z0-9_\.]*)\s+contains\s+(?P<rhs>.+)$",
        text,
    )
    if contains:
        lhs = _resolve_path(contains.group("lhs"), state=state, actor=actor)
        rhs = coerce_literal(contains.group("rhs"))
        if isinstance(lhs, list | tuple | set):
            return rhs in lhs
        return False
    # Bare truthy path
    return bool(_resolve_path(text, state=state, actor=actor))


def _resolve_path(path: str, *, state: dict[str, Any], actor: dict[str, Any]) -> Any:
    if path.startswith("state."):
        return state.get(path[len("state.") :])
    if path.startswith("actor."):
        return actor.get(path[len("actor.") :])
    if path in state:
        return state[path]
    if path in actor:
        return actor[path]
    return None
