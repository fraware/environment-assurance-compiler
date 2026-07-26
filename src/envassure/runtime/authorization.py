"""Authorization compiler — fail-closed (EAC-R04)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from envassure.ir.models import ActorDefinition

_ROLE_AUTH_RE = re.compile(r"^(?:role:|authz:|capability:)?(.+)$", re.IGNORECASE)


class AuthDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    INDETERMINATE = "indeterminate"


AuthKind = Literal[
    "role",
    "capability",
    "policy",
    "scope",
    "tenant",
    "grant",
    "delegation",
    "temporal",
    "authority",
    "and",
    "or",
]


@dataclass(frozen=True, slots=True)
class AuthExpr:
    """Typed authorization AST (atoms + boolean combinators)."""

    kind: AuthKind
    value: str | None = None
    temporal_op: str | None = None
    children: tuple[AuthExpr, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthResult:
    decision: AuthDecision
    reason: str
    reason_code: str
    node: AuthExpr | None = None


def normalize_auth_token(token: str) -> str:
    match = _ROLE_AUTH_RE.match(token.strip())
    return (match.group(1) if match else token).strip().lower()


def delegation_targets(rule: str) -> list[str]:
    """Parse delegation_rules into authority tokens."""
    rule_l = rule.strip().lower()
    for prefix in ("delegates:", "delegate:", "via:", "grant:", "from:", "to:"):
        if rule_l.startswith(prefix):
            return [normalize_auth_token(rule[len(prefix) :])]
    if "->" in rule:
        return [normalize_auth_token(part) for part in rule.split("->")]
    return [normalize_auth_token(rule)]


def actor_discharges(auth: str, actor: ActorDefinition) -> bool:
    """Return True when *actor* can discharge *auth* via authority/role/capability.

    Shared source of truth with static analysis (EAC-R04).
    """
    needle = normalize_auth_token(auth)
    for rev in actor.revocation_rules:
        if normalize_auth_token(rev) == needle:
            return False
    candidates: list[str] = []
    if actor.authority_source:
        candidates.append(actor.authority_source)
    candidates.extend(actor.roles)
    candidates.extend(actor.capabilities)
    candidates.extend(actor.credentials)
    for rule in actor.delegation_rules:
        candidates.extend(delegation_targets(rule))
    for cand in candidates:
        if normalize_auth_token(cand) == needle:
            return True
        if cand.strip().lower() == auth.strip().lower():
            return True
    return False


def compile_authorization(raw: str) -> AuthExpr:
    """Compile an authorization string into a typed AST (fail-closed on unknown)."""
    text = raw.strip()
    if not text:
        raise ValueError("empty authorization expression")
    return _parse_auth_or(text)


def _split_top(text: str, sep: str) -> list[str] | None:
    """Split on *sep* at top level (no nested parens)."""
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    i = 0
    sep_l = sep.lower()
    lower = text
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
            buf.append(ch)
            i += 1
            continue
        if ch == ")":
            depth -= 1
            buf.append(ch)
            i += 1
            continue
        if depth == 0 and lower[i : i + len(sep)].lower() == sep_l:
            # Word-boundary for bare keywords. Separators that already include
            # leading/trailing whitespace (e.g. " and " / " or ") provide their
            # own boundaries — do not also require a non-alnum neighbor, or
            # "role:ops and capability:read" fails to split (the 's' before the
            # space would reject the match).
            leading_ws = bool(sep[:1].isspace())
            trailing_ws = bool(sep[-1:].isspace())
            before_ok = leading_ws or i == 0 or not lower[i - 1].isalnum()
            after = i + len(sep)
            after_ok = trailing_ws or after >= len(text) or not lower[after].isalnum()
            if before_ok and after_ok:
                parts.append("".join(buf).strip())
                buf = []
                i = after
                continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())
    if len(parts) > 1:
        return [p for p in parts if p]
    return None


def _parse_auth_or(text: str) -> AuthExpr:
    parts = _split_top(text, " or ")
    if parts and len(parts) > 1:
        return AuthExpr(kind="or", children=tuple(_parse_auth_and(p) for p in parts))
    return _parse_auth_and(text)


def _parse_auth_and(text: str) -> AuthExpr:
    parts = _split_top(text, " and ")
    if parts and len(parts) > 1:
        return AuthExpr(kind="and", children=tuple(_parse_auth_atom(p) for p in parts))
    return _parse_auth_atom(text)


def _parse_auth_atom(text: str) -> AuthExpr:
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        return _parse_auth_or(text[1:-1].strip())

    lower = text.lower()
    if lower.startswith("temporal:"):
        rest = text.split(":", 1)[1]
        # temporal:before:ISO / temporal:after:ISO / temporal:expires:ISO
        if ":" in rest:
            op, _, value = rest.partition(":")
            op_l = op.strip().lower()
            if op_l not in {"before", "after", "expires"}:
                raise ValueError(f"unsupported temporal operator {op!r}")
            return AuthExpr(kind="temporal", value=value.strip(), temporal_op=op_l)
        raise ValueError(f"malformed temporal authorization: {text!r}")

    for prefix, kind in (
        ("role:", "role"),
        ("capability:", "capability"),
        ("policy:", "policy"),
        ("scope:", "scope"),
        ("tenant:", "tenant"),
        ("grant:", "grant"),
        ("delegation:", "delegation"),
        ("delegates:", "delegation"),
        ("authz:", "role"),
        ("authority:", "authority"),
    ):
        if lower.startswith(prefix):
            return AuthExpr(kind=kind, value=text[len(prefix) :].strip())  # type: ignore[arg-type]

    # Bare token without a known prefix is unsupported (fail closed) — unless it is
    # a historical bare role name already used in packs. Treat bare identifiers as
    # role requirements for compatibility with authority discharge tokens.
    if ":" not in text and text.replace("_", "").replace("-", "").isalnum():
        return AuthExpr(kind="role", value=text)

    raise ValueError(f"unsupported authorization form: {text!r}")


def evaluate_authorization(
    raw: str,
    *,
    actor: ActorDefinition,
    actor_view: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> AuthResult:
    """Evaluate authorization; unknown/unsupported → indeterminate (never allow)."""
    try:
        tree = compile_authorization(raw)
    except ValueError as exc:
        return AuthResult(
            decision=AuthDecision.INDETERMINATE,
            reason=str(exc),
            reason_code="indeterminate_unsupported_authorization",
        )
    return _eval_auth(tree, actor=actor, actor_view=actor_view, context=context or {})


def _eval_auth(
    node: AuthExpr,
    *,
    actor: ActorDefinition,
    actor_view: dict[str, Any],
    context: dict[str, Any],
) -> AuthResult:
    if node.kind == "and":
        for child in node.children:
            result = _eval_auth(child, actor=actor, actor_view=actor_view, context=context)
            if result.decision != AuthDecision.ALLOW:
                return result
        return AuthResult(AuthDecision.ALLOW, "all conjuncts satisfied", "authorized", node)
    if node.kind == "or":
        reasons: list[str] = []
        saw_indeterminate = False
        for child in node.children:
            result = _eval_auth(child, actor=actor, actor_view=actor_view, context=context)
            if result.decision == AuthDecision.ALLOW:
                return result
            if result.decision == AuthDecision.INDETERMINATE:
                saw_indeterminate = True
            reasons.append(result.reason)
        if saw_indeterminate:
            return AuthResult(
                AuthDecision.INDETERMINATE,
                "; ".join(reasons),
                "indeterminate_unsupported_authorization",
                node,
            )
        return AuthResult(
            AuthDecision.DENY,
            "; ".join(reasons) or "no disjunct satisfied",
            "authorization_denied",
            node,
        )

    if node.kind == "temporal":
        return _eval_temporal(node, context)

    assert node.value is not None
    # Revocation always wins.
    needle = normalize_auth_token(
        f"{node.kind}:{node.value}" if node.kind != "role" else node.value
    )
    for rev in list(actor.revocation_rules) + list(actor_view.get("revocation_rules") or []):
        if normalize_auth_token(str(rev)) == needle or normalize_auth_token(
            str(rev)
        ) == normalize_auth_token(node.value):
            return AuthResult(
                AuthDecision.DENY,
                f"authority {node.value!r} revoked",
                "authorization_revoked",
                node,
            )

    if node.kind in {"role", "capability", "authority", "grant", "delegation"}:
        # Discharge via shared actor_discharges for role/capability/authority tokens.
        token = node.value
        if node.kind == "role":
            check = f"role:{token}"
        elif node.kind == "capability":
            check = f"capability:{token}"
        elif node.kind == "grant":
            check = f"grant:{token}"
        elif node.kind == "delegation":
            check = f"delegation:{token}"
        else:
            check = token
        # Prefer IR discharge; also check runtime view expansions (scope grants etc.).
        if actor_discharges(check, actor) or actor_discharges(token, actor):
            return AuthResult(
                AuthDecision.ALLOW, f"{node.kind} {token!r} discharged", "authorized", node
            )
        # Runtime view may carry extra roles/capabilities injected at reset.
        view_roles = set(actor_view.get("roles") or [])
        view_caps = set(actor_view.get("capabilities") or [])
        view_creds = set(actor_view.get("credentials") or [])
        view_grants = set(actor_view.get("grants") or [])
        haystack = view_roles | view_caps | view_creds | view_grants
        if token in haystack or normalize_auth_token(token) in {
            normalize_auth_token(str(x)) for x in haystack
        }:
            return AuthResult(
                AuthDecision.ALLOW, f"{node.kind} {token!r} in actor view", "authorized", node
            )
        return AuthResult(
            AuthDecision.DENY,
            f"actor lacks required {node.kind} {token!r}",
            "authorization_denied",
            node,
        )

    if node.kind in {"tenant", "scope", "policy"}:
        required = node.value
        actual = actor_view.get(node.kind)
        if actual is None:
            # Fall back to credentials / roles tagged as tenant:X etc.
            tagged = f"{node.kind}:{required}"
            if actor_discharges(tagged, actor) or tagged in (actor_view.get("credentials") or []):
                return AuthResult(
                    AuthDecision.ALLOW,
                    f"{node.kind} {required!r} discharged",
                    "authorized",
                    node,
                )
            return AuthResult(
                AuthDecision.DENY,
                f"actor missing {node.kind} {required!r}",
                "authorization_denied",
                node,
            )
        if str(actual) == required or normalize_auth_token(str(actual)) == normalize_auth_token(
            required
        ):
            return AuthResult(
                AuthDecision.ALLOW,
                f"{node.kind} matches {required!r}",
                "authorized",
                node,
            )
        if node.kind == "scope":
            granted = str(actual)
            if granted == required or required.startswith(granted + "."):
                return AuthResult(
                    AuthDecision.ALLOW,
                    f"scope grant {granted!r} covers {required!r}",
                    "authorized",
                    node,
                )
            if granted.startswith(required + "."):
                return AuthResult(
                    AuthDecision.DENY,
                    f"scope expansion denied: have {granted!r}, need {required!r}",
                    "authorization_scope_expansion",
                    node,
                )
            return AuthResult(
                AuthDecision.DENY,
                f"actor scope {granted!r} does not cover {required!r}",
                "authorization_denied",
                node,
            )
        return AuthResult(
            AuthDecision.DENY,
            f"actor {node.kind} {actual!r} does not match {required!r}",
            "authorization_denied",
            node,
        )

    return AuthResult(
        AuthDecision.INDETERMINATE,
        f"unsupported authorization kind {node.kind!r}",
        "indeterminate_unsupported_authorization",
        node,
    )


def _eval_temporal(node: AuthExpr, context: dict[str, Any]) -> AuthResult:
    op = node.temporal_op or "expires"
    raw_limit = node.value or ""
    try:
        limit = _parse_time(raw_limit)
    except ValueError as exc:
        return AuthResult(
            AuthDecision.INDETERMINATE,
            f"unparseable temporal bound: {exc}",
            "indeterminate_unsupported_authorization",
            node,
        )
    now_raw = context.get("now") or context.get("clock_time")
    if now_raw is None:
        # Discrete clock environments may provide integer clock; treat missing as deny.
        return AuthResult(
            AuthDecision.DENY,
            "temporal authorization requires context.now",
            "authorization_temporal_missing_now",
            node,
        )
    try:
        now = _parse_time(str(now_raw)) if not isinstance(now_raw, datetime) else now_raw
    except ValueError:
        return AuthResult(
            AuthDecision.INDETERMINATE,
            f"unparseable context.now {now_raw!r}",
            "indeterminate_unsupported_authorization",
            node,
        )
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if limit.tzinfo is None:
        limit = limit.replace(tzinfo=UTC)

    ok = False
    if op == "before":
        ok = now < limit
    elif op == "after":
        ok = now > limit
    elif op == "expires":
        ok = now <= limit
    else:
        return AuthResult(
            AuthDecision.INDETERMINATE,
            f"unsupported temporal op {op!r}",
            "indeterminate_unsupported_authorization",
            node,
        )
    if ok:
        return AuthResult(AuthDecision.ALLOW, f"temporal {op} satisfied", "authorized", node)
    return AuthResult(
        AuthDecision.DENY,
        f"temporal {op} failed (now={now.isoformat()}, limit={limit.isoformat()})",
        "authorization_expired",
        node,
    )


def _parse_time(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)
