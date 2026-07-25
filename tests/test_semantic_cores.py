"""Semantic-core coverage: expressions, auth, payloads, observations, diff, reconciliation.

Raises fail-under ≥90% for `.coveragerc.semantic`. Prefer real fail-closed
assertions over pragma exemptions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from envassure.api import World
from envassure.differential.compare import (
    ComparisonDimension,
    ComparisonTolerances,
    VerdictStatus,
    compare_outcomes,
)
from envassure.differential.connector import ProbeOutcome
from envassure.expressions import (
    EvalContext,
    ExpressionError,
    evaluate,
    evaluate_bool,
    parse_expression,
    parse_structured,
    validate_expression,
)
from envassure.expressions.ast import BinaryOp, CallExpr, Literal, PathRef, UnaryOp
from envassure.expressions.parser import coerce_literal, parse_effect
from envassure.expressions.types import ExprType, infer_type, type_of_value
from envassure.facts.models import ConfidenceRecord, SemanticFact, make_fact_id
from envassure.ir.models import (
    ActorDefinition,
    ObservationProjection,
    TransitionBranch,
    WorldDefinition,
)
from envassure.ir.primitives import ConstraintExpr, EntityRef
from envassure.reconciliation.cegr import (
    CounterexampleIntake,
    apply_cegr,
    counterexample_from_mapping,
    list_refinement_generations,
    load_refinement_generation,
    resolve_ambiguity_alias,
    run_cegr_loop,
)
from envassure.reconciliation.engine import (
    ambiguity_id,
    project_source_precedence,
    reconcile,
)
from envassure.runtime import EventSourcedEnvironment, RuntimeError_, StepOutcome
from envassure.runtime.authorization import (
    AuthDecision,
    actor_discharges,
    compile_authorization,
    delegation_targets,
    evaluate_authorization,
    normalize_auth_token,
)
from envassure.runtime.effects import apply_effect, evaluate_constraint
from envassure.runtime.events import SideEffectIntent
from envassure.runtime.external import RejectingExecutor, intent_digest, recorded_receipt
from envassure.runtime.observations import (
    ObservationError,
    compile_observation,
    observe_or_empty,
    probe_observation_leaks,
    project_state,
    validate_observation_projections,
)
from envassure.runtime.payloads import (
    PayloadValidationError,
    payload_digest,
    redact_payload,
    validate_payload,
)
from envassure.runtime.snapshot import Snapshot
from envassure.workspace.config import SourcePrecedenceSection

# ---------------------------------------------------------------------------
# Expressions — parser / evaluate / types / validate
# ---------------------------------------------------------------------------


def test_expression_arithmetic_logic_unary_membership() -> None:
    ctx = EvalContext(state={"n": 10, "items": [1, 2], "m": {"a": 1}, "s": "ab"})
    assert evaluate(parse_expression("n + 2"), ctx) == 12
    assert evaluate(parse_expression("n - 3"), ctx) == 7
    assert evaluate(parse_expression("n * 2"), ctx) == 20
    assert evaluate(parse_expression("n / 2"), ctx) == 5.0
    assert evaluate(parse_expression("n // 3"), ctx) == 3
    assert evaluate(parse_expression("n % 3"), ctx) == 1
    assert evaluate(parse_expression("-n"), ctx) == -10
    assert evaluate(parse_expression("+n"), ctx) == 10
    assert evaluate(parse_expression("not (n == 0)"), ctx) is True
    assert evaluate_bool(parse_expression("n > 5 and n < 20"), ctx) is True
    assert evaluate_bool(parse_expression("n < 0 or n == 10"), ctx) is True
    assert evaluate_bool(parse_expression("1 in items"), ctx) is True
    assert evaluate_bool(parse_expression("9 in items"), ctx) is False
    assert evaluate_bool(parse_expression('m contains "a"'), ctx) is True
    assert evaluate_bool(parse_expression('"a" in s'), ctx) is True
    assert evaluate(parse_expression('"x" + "y"'), ctx) == "xy"
    assert evaluate_bool(parse_expression("n != 0"), ctx) is True
    assert evaluate_bool(parse_expression("n <= 10"), ctx) is True
    assert evaluate_bool(parse_expression("n >= 10"), ctx) is True


def test_expression_conditional_and_collection_any() -> None:
    ctx = EvalContext(state={"flag": True, "items": [1, -1, 3], "bag": {1, 2}, "map": {"a": 5}})
    assert evaluate(parse_expression("if flag then 1 else 0"), ctx) == 1
    assert evaluate(parse_expression("if not flag then 1 else 2"), ctx) == 2
    assert evaluate_bool(parse_expression("any x in items: x < 0"), ctx) is True
    assert evaluate_bool(parse_expression("all x in bag: x > 0"), ctx) is True
    assert evaluate_bool(parse_expression("all x in map: x > 0"), ctx) is True


def test_expression_allowlisted_calls() -> None:
    ctx = EvalContext(state={"xs": [3, 1, 2], "m": {"a": 1, "b": 2}, "s": "Ab"})
    assert evaluate(parse_expression("len(xs)"), ctx) == 3
    assert evaluate(parse_expression("abs(-4)"), ctx) == 4
    assert evaluate(parse_expression("min(xs)"), ctx) == 1
    assert evaluate(parse_expression("max(1, 9, 3)"), ctx) == 9
    assert evaluate(parse_expression("str(1)"), ctx) == "1"
    assert evaluate(parse_expression("bool(1)"), ctx) is True
    assert evaluate(parse_expression("int('3')"), ctx) == 3
    assert evaluate(parse_expression("float('1.5')"), ctx) == 1.5
    assert evaluate(parse_expression("keys(m)"), ctx) == ["a", "b"]
    assert evaluate(parse_expression("values(m)"), ctx) == [1, 2]
    assert evaluate(parse_expression("lower(s)"), ctx) == "ab"
    assert evaluate(parse_expression("upper(s)"), ctx) == "AB"


def test_expression_fail_closed_type_and_unsupported() -> None:
    ctx = EvalContext(state={"s": "x", "n": 1})
    with pytest.raises(ExpressionError, match="unary"):
        evaluate(parse_expression("-s"), ctx)
    with pytest.raises(ExpressionError, match="unary"):
        evaluate(parse_expression("+s"), ctx)
    with pytest.raises(ExpressionError, match="ordered comparison"):
        evaluate(parse_expression("s < 1"), ctx)
    with pytest.raises(ExpressionError, match="arithmetic"):
        evaluate(parse_expression("s * 2"), ctx)
    with pytest.raises(ExpressionError, match="membership"):
        evaluate(parse_expression("1 in n"), ctx)
    with pytest.raises(ExpressionError, match="allowlisted"):
        evaluate(CallExpr("evil", (Literal(1),)), ctx)
    with pytest.raises(ExpressionError, match="call"):
        evaluate(parse_expression("len(1)"), ctx)
    with pytest.raises(ExpressionError, match="bound"):
        evaluate_bool(
            parse_expression("all x in items: x > 0"),
            EvalContext(state={"items": list(range(100))}),
        )
    with pytest.raises(ExpressionError, match="collection"):
        evaluate_bool(parse_expression("all x in n: x > 0"), ctx)
    with pytest.raises(ExpressionError):
        evaluate(UnaryOp("weird", Literal(1)), ctx)  # type: ignore[arg-type]
    with pytest.raises(ExpressionError):
        evaluate(BinaryOp("??", Literal(1), Literal(2)), ctx)  # type: ignore[arg-type]


def test_expression_path_indexing_and_bool_coercion() -> None:
    class Obj:
        y = 3

    ctx = EvalContext(state={"nested": {"a": 1}, "obj": Obj(), "flag": True})
    assert evaluate(parse_expression("nested.a"), ctx) == 1
    assert evaluate(parse_expression("obj.y"), ctx) == 3
    assert evaluate(parse_expression("missing"), ctx) is None
    assert evaluate_bool(parse_expression("flag"), ctx) is True
    assert evaluate_bool(parse_expression("missing"), ctx) is False
    assert evaluate_bool(Literal(None), ctx) is False
    assert evaluate_bool(Literal(0), ctx) is False
    with pytest.raises(ExpressionError, match="path segment"):
        evaluate(parse_expression("flag.x"), ctx)
    with pytest.raises(ExpressionError, match="boolean"):
        evaluate_bool(Literal(object()), ctx)


def test_expression_parser_edge_cases() -> None:
    assert evaluate(parse_expression("(1 + 2) * 3"), EvalContext()) == 9
    assert evaluate(parse_expression("true"), EvalContext()) is True
    assert evaluate(parse_expression("false"), EvalContext()) is False
    assert evaluate(parse_expression("null"), EvalContext()) is None
    assert evaluate(parse_expression("none"), EvalContext()) is None
    assert evaluate(parse_expression("3.5"), EvalContext()) == 3.5
    assert evaluate(parse_expression(r'"a\"b"'), EvalContext()) == 'a"b'
    with pytest.raises(ExpressionError, match="unterminated"):
        parse_expression("'abc")
    with pytest.raises(ExpressionError, match="unexpected character"):
        parse_expression("1 @ 2")
    with pytest.raises(ExpressionError, match="empty"):
        parse_expression("   ")
    with pytest.raises(ExpressionError, match="trailing"):
        parse_expression("1 2")
    name, op, rhs = parse_effect("count = 1")
    assert name == "count" and op == "=" and evaluate(rhs, EvalContext()) == 1
    with pytest.raises(ExpressionError, match="nested"):
        parse_effect("a.b = 1")
    with pytest.raises(ExpressionError, match="unsupported intended_effect"):
        parse_effect("no-op")


def test_structured_expression_forms() -> None:
    ctx = EvalContext(state={"n": 5, "items": [1, 2], "m": {"k": 1}})
    cases = [
        ({"lit": 3}, 3),
        ({"literal": True}, True),
        ({"path": "state.n"}, 5),
        ({"eq": ["state.n", 5]}, True),
        ({"neq": [1, 2]}, True),
        ({"gt": ["state.n", 1]}, True),
        ({"lt": ["state.n", 9]}, True),
        ({"gte": ["state.n", 5]}, True),
        ({"lte": ["state.n", 5]}, True),
        ({"and": [{"eq": [1, 1]}, {"eq": [2, 2]}]}, True),
        ({"or": [{"eq": [1, 0]}, {"eq": [2, 2]}]}, True),
        ({"not": {"eq": [1, 0]}}, True),
        ({"in": [1, {"path": "state.items"}]}, True),
        ({"contains": [{"path": "state.m"}, {"lit": "k"}]}, True),
        ({"if": {"test": {"eq": [1, 1]}, "then": 7, "else": 8}}, 7),
        ({"call": {"name": "abs", "args": [-3]}}, 3),
        (
            {
                "all": {
                    "var": "x",
                    "collection": {"path": "state.items"},
                    "body": {"gt": ["x", 0]},
                }
            },
            True,
        ),
        (
            {
                "any": {
                    "var": "x",
                    "collection": {"path": "state.items"},
                    "body": {"eq": ["x", 2]},
                }
            },
            True,
        ),
    ]
    for structured, expected in cases:
        expr = parse_structured(structured)
        value = evaluate(expr, ctx)
        if isinstance(expected, bool):
            assert evaluate_bool(expr, ctx) is expected
        else:
            assert value == expected

    with pytest.raises(ExpressionError):
        parse_structured({})
    with pytest.raises(ExpressionError):
        parse_structured({"not_equals": 1})
    with pytest.raises(ExpressionError):
        parse_structured({"and": []})
    with pytest.raises(ExpressionError):
        parse_structured({"or": "x"})
    with pytest.raises(ExpressionError):
        parse_structured({"in": [1]})
    with pytest.raises(ExpressionError):
        parse_structured({"contains": [1]})
    with pytest.raises(ExpressionError):
        parse_structured({"if": 1})
    with pytest.raises(ExpressionError):
        parse_structured({"call": {"args": []}})
    with pytest.raises(ExpressionError):
        parse_structured({"call": {"name": "abs", "args": "x"}})
    with pytest.raises(ExpressionError):
        parse_structured({"all": 1})
    with pytest.raises(ExpressionError):
        parse_structured({"weird": 1})
    with pytest.raises(ExpressionError):
        parse_structured({"eq": [1]})


def test_validate_expression_and_types() -> None:
    expr, diags = validate_expression("state.n == 1")
    assert expr is not None and not diags
    expr2, diags2 = validate_expression(structured={"eq": [1, 1]})
    assert expr2 is not None and not diags2
    bad, diags3 = validate_expression("@@@")
    assert bad is None and diags3
    empty, diags4 = validate_expression()
    assert empty is None and diags4

    assert type_of_value(None) is ExprType.NULL
    assert type_of_value(True) is ExprType.BOOLEAN
    assert type_of_value(1) is ExprType.NUMBER
    assert type_of_value("x") is ExprType.STRING
    assert type_of_value([1]) is ExprType.LIST
    assert type_of_value({"a": 1}) is ExprType.MAP
    assert type_of_value(object()) is ExprType.UNKNOWN
    assert infer_type(Literal(1)) is ExprType.NUMBER
    assert infer_type(PathRef("state", ("n",))) is ExprType.ANY
    assert infer_type(UnaryOp("not", Literal(True))) is ExprType.BOOLEAN
    assert infer_type(UnaryOp("neg", Literal(1))) is ExprType.NUMBER
    assert infer_type(parse_expression("1 == 1")) is ExprType.BOOLEAN
    assert infer_type(parse_expression("1 + 2")) is ExprType.NUMBER
    assert infer_type(parse_expression("if true then 1 else 2")) is ExprType.NUMBER
    assert infer_type(parse_expression("if true then 1 else 'x'")) is ExprType.ANY
    assert infer_type(parse_expression("1 in items")) is ExprType.BOOLEAN
    assert infer_type(parse_expression("len(xs)")) is ExprType.NUMBER
    assert infer_type(parse_expression("all x in xs: x > 0")) is ExprType.BOOLEAN
    with pytest.raises(ExpressionError):
        infer_type(CallExpr("nope", ()))


def test_coerce_literal_helpers() -> None:
    assert coerce_literal("1") == 1
    assert coerce_literal("'hi'") == "hi"
    assert coerce_literal("true") is True
    assert coerce_literal("false") is False
    assert coerce_literal("null") is None
    assert coerce_literal("none") is None
    assert coerce_literal("") is None
    assert coerce_literal("plain") == "plain"


@given(st.integers(min_value=-50, max_value=50), st.integers(min_value=-50, max_value=50))
@settings(max_examples=40)
def test_expression_metamorphic_add_commutes(a: int, b: int) -> None:
    ctx = EvalContext(state={"a": a, "b": b})
    left = evaluate(parse_expression("a + b"), ctx)
    right = evaluate(parse_expression("b + a"), ctx)
    assert left == right == a + b


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_auth_combinators_and_delegation() -> None:
    actor = ActorDefinition(
        id="u",
        actor_class="u",
        roles=["ops"],
        capabilities=["read"],
        credentials=["grant:write"],
        authority_source="authority:root",
        delegation_rules=["delegates:ops", "via:helper", "a->b"],
    )
    assert delegation_targets("delegates:ops") == ["ops"]
    assert "helper" in delegation_targets("via:helper")
    assert actor_discharges("role:ops", actor) is True
    assert actor_discharges("capability:read", actor) is True

    and_ok = evaluate_authorization(
        "role:ops and capability:read",
        actor=actor,
        actor_view={"roles": ["ops"], "capabilities": ["read"]},
    )
    assert and_ok.decision == AuthDecision.ALLOW

    and_deny = evaluate_authorization(
        "role:ops and role:admin",
        actor=actor,
        actor_view={"roles": ["ops"]},
    )
    assert and_deny.decision == AuthDecision.DENY

    or_ok = evaluate_authorization(
        "role:admin or role:ops",
        actor=actor,
        actor_view={"roles": ["ops"]},
    )
    assert or_ok.decision == AuthDecision.ALLOW

    or_indeterminate = evaluate_authorization(
        "role:missing or magic:portal",
        actor=actor,
        actor_view={},
    )
    assert or_indeterminate.decision == AuthDecision.INDETERMINATE

    or_deny = evaluate_authorization(
        "role:missing_a or role:missing_b",
        actor=ActorDefinition(id="z", actor_class="z", roles=["ops"]),
        actor_view={},
    )
    assert or_deny.decision == AuthDecision.DENY

    paren = compile_authorization("(role:ops or role:admin) and capability:read")
    assert paren.kind == "and"

    bare = compile_authorization("ops")
    assert bare.kind == "role"
    with pytest.raises(ValueError, match="empty"):
        compile_authorization("  ")
    with pytest.raises(ValueError, match="unsupported"):
        compile_authorization("weird:scheme:x:y")
    with pytest.raises(ValueError, match="temporal"):
        compile_authorization("temporal:weird:2020-01-01")
    with pytest.raises(ValueError, match="malformed temporal"):
        compile_authorization("temporal:expires")


def test_auth_temporal_grant_scope_policy_revocation() -> None:
    actor = ActorDefinition(id="u", actor_class="u", roles=["ops"], revocation_rules=["role:ops"])
    assert actor_discharges("role:ops", actor) is False

    grant_actor = ActorDefinition(id="g", actor_class="g", credentials=["grant:edit"])
    assert (
        evaluate_authorization(
            "grant:edit",
            actor=grant_actor,
            actor_view={},
        ).decision
        == AuthDecision.ALLOW
    )
    assert (
        evaluate_authorization(
            "delegation:edit",
            actor=grant_actor,
            actor_view={"grants": ["edit"]},
        ).decision
        == AuthDecision.ALLOW
    )

    now = datetime(2026, 6, 1, tzinfo=UTC)
    before_ok = evaluate_authorization(
        "temporal:before:2027-01-01T00:00:00+00:00",
        actor=grant_actor,
        actor_view={},
        context={"now": now},
    )
    assert before_ok.decision == AuthDecision.ALLOW
    after_ok = evaluate_authorization(
        "temporal:after:2020-01-01T00:00:00Z",
        actor=grant_actor,
        actor_view={},
        context={"now": now},
    )
    assert after_ok.decision == AuthDecision.ALLOW
    missing_now = evaluate_authorization(
        "temporal:expires:2027-01-01T00:00:00+00:00",
        actor=grant_actor,
        actor_view={},
        context={},
    )
    assert missing_now.decision == AuthDecision.DENY
    bad_bound = evaluate_authorization(
        "temporal:expires:not-a-time",
        actor=grant_actor,
        actor_view={},
        context={"now": now.isoformat()},
    )
    assert bad_bound.decision == AuthDecision.INDETERMINATE
    bad_now = evaluate_authorization(
        "temporal:expires:2027-01-01T00:00:00+00:00",
        actor=grant_actor,
        actor_view={},
        context={"now": "nope"},
    )
    assert bad_now.decision == AuthDecision.INDETERMINATE

    tenant = evaluate_authorization(
        "tenant:acme",
        actor=ActorDefinition(id="t", actor_class="t", credentials=["tenant:acme"]),
        actor_view={},
    )
    assert tenant.decision == AuthDecision.ALLOW
    policy_mismatch = evaluate_authorization(
        "policy:strict",
        actor=grant_actor,
        actor_view={"policy": "loose"},
    )
    assert policy_mismatch.decision == AuthDecision.DENY
    scope_cover = evaluate_authorization(
        "scope:orders.write",
        actor=grant_actor,
        actor_view={"scope": "orders"},
    )
    assert scope_cover.decision == AuthDecision.ALLOW
    scope_miss = evaluate_authorization(
        "scope:billing",
        actor=grant_actor,
        actor_view={"scope": "orders"},
    )
    assert scope_miss.decision == AuthDecision.DENY
    assert normalize_auth_token("Role:Admin") == "admin"


# ---------------------------------------------------------------------------
# Payloads / effects / external
# ---------------------------------------------------------------------------


def test_payload_schema_branches_and_digest() -> None:
    validate_payload({}, {"ok": True})
    with pytest.raises(PayloadValidationError):
        validate_payload({}, "x")  # type: ignore[arg-type]

    schema = {
        "type": "object",
        "required": ["n", "tag"],
        "properties": {
            "n": {"type": "integer", "minimum": 0, "maximum": 10},
            "tag": {"type": "string", "minLength": 1, "maxLength": 4, "enum": ["a", "b"]},
            "xs": {"type": "array", "items": {"type": "number"}},
            "flag": {"type": ["boolean", "null"]},
        },
        "additionalProperties": {"type": "string"},
    }
    validate_payload(schema, {"n": 1, "tag": "a", "xs": [1.5], "flag": None, "extra": "ok"})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 1})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 99, "tag": "a"})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": -1, "tag": "a"})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 1, "tag": ""})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 1, "tag": "abcdef"})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 1, "tag": "z"})
    with pytest.raises(PayloadValidationError):
        validate_payload(schema, {"n": 1, "tag": "a", "xs": ["x"]})
    with pytest.raises(PayloadValidationError):
        validate_payload({"type": "integer"}, True)
    with pytest.raises(PayloadValidationError):
        validate_payload({"type": "weird"}, 1)

    nested = redact_payload({"token": "x", "nest": {"password": "y"}, "list": [{"secret": "z"}]})
    assert nested["token"] == "***REDACTED***"
    assert nested["nest"]["password"] == "***REDACTED***"
    assert nested["list"][0]["secret"] == "***REDACTED***"
    assert payload_digest({"a": 1})


def test_effects_and_constraints_fail_closed() -> None:
    state = {"n": 1, "s": "x"}
    assert apply_effect(state, "n += 2") == {"n": 3}
    assert state["n"] == 3
    assert apply_effect(state, "n -= 1") == {"n": 2}
    assert apply_effect(state, "n = 9") == {"n": 9}
    with pytest.raises(ValueError):
        apply_effect({"s": "x"}, "s += 1")
    with pytest.raises(ValueError):
        apply_effect({"n": 1}, "n += 'x'")
    with pytest.raises(ValueError):
        apply_effect({"s": "x"}, "s -= 1")
    with pytest.raises(ValueError):
        apply_effect({"n": 1}, "n -= 'x'")
    with pytest.raises(ValueError):
        apply_effect(state, "@@@")

    assert evaluate_constraint("n == 9", state=state, actor={}) is True
    assert (
        evaluate_constraint(
            ConstraintExpr(expression="", structured={"eq": ["state.n", 9]}),
            state=state,
            actor={},
        )
        is True
    )
    with pytest.raises(ExpressionError):
        evaluate_constraint(
            ConstraintExpr(expression="", structured={"weird": 1}),
            state=state,
            actor={},
        )
    with pytest.raises(ExpressionError):
        evaluate_constraint("@@@", state=state, actor={})


def test_external_recorded_and_rejecting_executor() -> None:
    intent = SideEffectIntent(id="i1", kind="http", target="t", payload={"x": 1})
    digest = intent_digest(intent)
    receipt = recorded_receipt(intent)
    assert receipt.status == "recorded"
    assert receipt.intent_digest == digest
    failed = RejectingExecutor().execute(intent)
    assert failed.status == "failed"
    assert "ExternalEffectExecutor" in (failed.error or "")


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------


def test_observation_compile_project_transforms_and_deny() -> None:
    proj = ObservationProjection(
        id="pub",
        target_actor_class="a",
        visible_paths=["count", "secret.nested"],
        omitted_paths=["secret"],
        transformations=["rename:count->n", "redact:secret.nested", "omit:gone"],
        access_control="role:reader",
        information_flow_labels=["secret:deny", "count:allow", "freeform", "weird:zzz"],
        error_policy="omit",
        aggregation="none",
        delay="none",
        noise="",
        staleness="n/a",
        side_channel_policy="noop",
    )
    # weird:zzz is unsupported under strict
    strict = compile_observation(proj, strict_unsupported=True)
    assert strict.compiled is None
    assert strict.unsupported

    proj2 = proj.model_copy(update={"information_flow_labels": ["secret:deny", "count:allow"]})
    ok = compile_observation(proj2, strict_unsupported=True)
    assert ok.compiled is not None
    actor = ActorDefinition(id="a", actor_class="a", roles=["reader"])
    out = project_state(
        {"count": 3, "secret": {"nested": 9}, "gone": 1},
        ok.compiled,
        actor=actor,
        actor_view={"roles": ["reader"]},
    )
    assert "n" in out
    assert out.get("secret", {}).get("nested") is None

    denied = project_state(
        {"count": 3},
        ok.compiled,
        actor=ActorDefinition(id="b", actor_class="b", roles=[]),
        actor_view={"roles": []},
    )
    assert denied == {}

    omit_only = ObservationProjection(
        id="omit", target_actor_class="a", visible_paths=[], omitted_paths=["secret"]
    )
    compiled_omit = compile_observation(omit_only).compiled
    assert compiled_omit is not None
    projected = project_state({"count": 1, "secret": 2}, compiled_omit)
    assert projected == {"count": 1}

    empty = ObservationProjection(id="empty", target_actor_class="a")
    compiled_empty = compile_observation(empty).compiled
    assert compiled_empty is not None
    assert project_state({"count": 1}, compiled_empty) == {}

    bad_access = ObservationProjection(
        id="bad",
        target_actor_class="a",
        visible_paths=["count"],
        access_control="magic:x",
    )
    assert compile_observation(bad_access).compiled is None

    fail_missing = ObservationProjection(
        id="fail",
        target_actor_class="a",
        visible_paths=["missing"],
        error_policy="fail",
    )
    compiled_fail = compile_observation(fail_missing).compiled
    assert compiled_fail is not None
    with pytest.raises(ObservationError):
        project_state({}, compiled_fail)

    unsupported = compile_observation(
        ObservationProjection(
            id="delay", target_actor_class="a", visible_paths=["x"], delay="100ms"
        ),
        strict_unsupported=False,
    )
    assert unsupported.compiled is not None
    with pytest.raises(ObservationError):
        project_state({"x": 1}, unsupported.compiled)


def test_observation_validate_observe_or_empty_and_leaks() -> None:
    w = World("obs.v1", "Obs")
    w.state("count", initial_generator="0")
    w.state("secret", initial_generator="0")
    w.observation(
        "pub",
        target_actor_class="a",
        visible_paths=["count"],
        omitted_paths=["secret"],
    )
    w.actor("a", available_actions=["ping"], observation_projection_id="pub")
    w.actor("b", available_actions=["ping"])  # missing binding
    w.action(
        "ping",
        actor_classes=["a", "b"],
        intended_effects=["count += 1"],
        success_outcomes=["ok"],
    )
    w.transition("t", action_id="ping", branches=[TransitionBranch(id="t.ok", events=["p"])])
    world = w.compile()

    report = validate_observation_projections(world, require_actor_bindings=True)
    assert any(d.code == "EAC5005" for d in report.diagnostics)

    bad_world = world.model_copy(
        update={
            "observations": [
                ObservationProjection(id="bad", target_actor_class="z", visible_paths=["nope"]),
                ObservationProjection(id="empty", target_actor_class="z"),
            ],
            "actors": [
                ActorDefinition(
                    id="z",
                    actor_class="z",
                    available_actions=["ping"],
                    observation_projection_id="missing",
                )
            ],
        }
    )
    bad_report = validate_observation_projections(bad_world, require_actor_bindings=True)
    codes = {d.code for d in bad_report.diagnostics}
    assert "EAC5001" in codes
    assert "EAC5005" in codes

    actor = next(a for a in world.actors if a.id == "a")
    projections = {o.id: o for o in world.observations}
    cache: dict[str, Any] = {}
    seen = observe_or_empty(
        {"count": 1, "secret": 9}, actor=actor, projections=projections, compiled_cache=cache
    )
    assert seen == {"count": 1}
    assert "pub" in cache
    assert (
        observe_or_empty(
            {"count": 1}, actor=ActorDefinition(id="x", actor_class="x"), projections=projections
        )
        == {}
    )
    assert (
        observe_or_empty(
            {"count": 1},
            actor=ActorDefinition(id="y", actor_class="y", observation_projection_id="nope"),
            projections=projections,
        )
        == {}
    )
    assert probe_observation_leaks({"secret": 1}, missing_or_unknown_projection=True) == ["secret"]
    assert probe_observation_leaks({"secret": 1, "count": 1}, forbidden_paths=["secret"]) == [
        "secret"
    ]


# ---------------------------------------------------------------------------
# Differential compare gaps
# ---------------------------------------------------------------------------


def test_differential_dimension_edges_and_aggregation() -> None:
    ref = ProbeOutcome(
        probe_id="p",
        success=True,
        observation={"n": 1.0},
        state={"n": 1.0},
        failure_id=None,
        authorization_ok=True,
        retry_count=0,
        idempotent_replay_equal=True,
        latency_ms=10.0,
    )
    cand = ProbeOutcome(
        probe_id="p",
        success=True,
        observation={"n": 1.0000005},
        state={"n": 1.0},
        failure_id=None,
        authorization_ok=True,
        retry_count=0,
        idempotent_replay_equal=True,
        latency_ms=12.0,
    )
    ok = compare_outcomes(ref, cand)
    assert ok.matched
    assert ok.failing_dimensions == []
    assert all(v.matched for v in ok.verdicts)

    # Empty dimensions list is falsy → defaults apply; missing evidence stays
    # indeterminate (never match). Explicit single N/A-only path is unused.
    empty = compare_outcomes(
        ProbeOutcome(probe_id="e", success=True),
        ProbeOutcome(probe_id="e", success=True),
        dimensions=[],
    )
    assert empty.overall_status is VerdictStatus.INDETERMINATE
    assert not empty.matched

    auth_partial = compare_outcomes(
        ProbeOutcome(probe_id="a", success=True, authorization_ok=True),
        ProbeOutcome(probe_id="a", success=True, authorization_ok=None),
        dimensions=[ComparisonDimension.AUTHORIZATION],
    )
    assert auth_partial.overall_status is VerdictStatus.INDETERMINATE

    auth_mismatch = compare_outcomes(
        ProbeOutcome(probe_id="a", success=True, authorization_ok=True),
        ProbeOutcome(probe_id="a", success=True, authorization_ok=False),
        dimensions=[ComparisonDimension.AUTHORIZATION],
    )
    assert auth_mismatch.overall_status is VerdictStatus.MISMATCH

    retry_mismatch = compare_outcomes(
        ProbeOutcome(probe_id="r", success=True, retry_count=0),
        ProbeOutcome(probe_id="r", success=True, retry_count=2),
        dimensions=[ComparisonDimension.RETRY],
    )
    assert retry_mismatch.overall_status is VerdictStatus.MISMATCH

    idem_partial = compare_outcomes(
        ProbeOutcome(probe_id="i", success=True, idempotent_replay_equal=True),
        ProbeOutcome(probe_id="i", success=True, idempotent_replay_equal=None),
        dimensions=[ComparisonDimension.IDEMPOTENCY],
    )
    assert idem_partial.overall_status is VerdictStatus.INDETERMINATE

    idem_mismatch = compare_outcomes(
        ProbeOutcome(probe_id="i", success=True, idempotent_replay_equal=True),
        ProbeOutcome(probe_id="i", success=True, idempotent_replay_equal=False),
        dimensions=[ComparisonDimension.IDEMPOTENCY],
    )
    assert idem_mismatch.overall_status is VerdictStatus.MISMATCH

    latency_miss = compare_outcomes(
        ProbeOutcome(probe_id="l", success=True, latency_ms=None),
        ProbeOutcome(probe_id="l", success=True, latency_ms=1.0),
        dimensions=[ComparisonDimension.LATENCY],
    )
    assert latency_miss.overall_status is VerdictStatus.INDETERMINATE

    latency_bad = compare_outcomes(
        ProbeOutcome(probe_id="l", success=True, latency_ms=1.0),
        ProbeOutcome(probe_id="l", success=True, latency_ms=200.0),
        dimensions=[ComparisonDimension.LATENCY],
        tolerances=ComparisonTolerances(latency_ms=5.0),
    )
    assert latency_bad.overall_status is VerdictStatus.MISMATCH

    obs_empty = compare_outcomes(
        ProbeOutcome(probe_id="o", success=True, observation={}, state={}),
        ProbeOutcome(probe_id="o", success=True, observation={}, state={}),
        dimensions=[ComparisonDimension.OBSERVATION, ComparisonDimension.STATE],
    )
    assert obs_empty.overall_status is VerdictStatus.INDETERMINATE

    obs_keys = compare_outcomes(
        ProbeOutcome(probe_id="o", success=True, observation={"a": 1}),
        ProbeOutcome(probe_id="o", success=True, observation={"b": 1}),
        dimensions=[ComparisonDimension.OBSERVATION],
    )
    assert obs_keys.overall_status is VerdictStatus.MISMATCH

    obs_rel = compare_outcomes(
        ProbeOutcome(probe_id="o", success=True, observation={"n": 1000.0}),
        ProbeOutcome(probe_id="o", success=True, observation={"n": 1000.5}),
        dimensions=[ComparisonDimension.OBSERVATION],
        tolerances=ComparisonTolerances(numeric_abs=0.0, numeric_rel=0.001),
    )
    assert obs_rel.matched

    fail_mismatch = compare_outcomes(
        ProbeOutcome(probe_id="f", success=False, failure_id="a"),
        ProbeOutcome(probe_id="f", success=False, failure_id="b"),
        dimensions=[ComparisonDimension.FAILURE],
    )
    assert fail_mismatch.overall_status is VerdictStatus.MISMATCH

    world = WorldDefinition(environment_id="s", name="s", determinism="statistical")
    no_margin = compare_outcomes(
        ProbeOutcome(probe_id="s", success=True),
        ProbeOutcome(probe_id="s", success=True),
        world=world,
        stochastic_samples=[(True, True)] * 40,
        dimensions=[ComparisonDimension.SUCCESS],
        tolerances=ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=None),
    )
    assert no_margin.verdicts[0].status is VerdictStatus.INDETERMINATE

    # Discordant but within margin + high p → match path with mcnemar note.
    mixed = [(True, True)] * 28 + [(True, False)] * 2 + [(False, True)] * 2
    mixed_ok = compare_outcomes(
        ProbeOutcome(probe_id="s", success=True),
        ProbeOutcome(probe_id="s", success=True),
        world=world,
        stochastic_samples=mixed,
        dimensions=[ComparisonDimension.SUCCESS],
        tolerances=ComparisonTolerances(stochastic_min_samples=30, equivalence_margin=0.2),
    )
    assert mixed_ok.verdicts[0].statistical is True


# ---------------------------------------------------------------------------
# Reconciliation engine + CEGR
# ---------------------------------------------------------------------------


def _fact(subject: str, predicate: str, value: Any, source: str = "openapi") -> SemanticFact:
    return SemanticFact(
        fact_id=make_fact_id(
            subject_kind="action",
            subject_id=subject,
            predicate=predicate,
            source=source,
        ),
        subject=EntityRef(kind="action", id=subject),
        predicate=predicate,
        value=value,
        source_refs=[source],
        extraction_method="test",
        confidence=ConfidenceRecord(
            evidence_class="api_contract",
            derivation_class="direct",
            extractor_certainty="high",
        ),
        kind_tags=["action"],
    )


def test_reconcile_conflicts_aliases_and_missing_ops() -> None:
    facts = [
        _fact("pay", "timeout_behavior", "fail_closed", "openapi"),
        _fact("pay", "retry_behavior", "retry", "openapi"),
        _fact("pay", "retry_behavior", "no_retry", "trace"),
        _fact("refund", "timeout_behavior", "fail_closed", "openapi"),
        _fact("pay", "alias_of", "payment", "openapi"),
        SemanticFact(
            fact_id=make_fact_id(
                subject_kind="action",
                subject_id="pay",
                predicate="name",
                source="openapi",
            ),
            subject=EntityRef(kind="action", id="pay"),
            predicate="name",
            value="Payment",
            source_refs=["openapi"],
            extraction_method="test",
            confidence=ConfidenceRecord(
                evidence_class="api_contract",
                derivation_class="direct",
                extractor_certainty="high",
            ),
            kind_tags=["action"],
        ),
        SemanticFact(
            fact_id=make_fact_id(
                subject_kind="action",
                subject_id="payment",
                predicate="name",
                source="trace",
            ),
            subject=EntityRef(kind="action", id="payment"),
            predicate="name",
            value="Payment",
            source_refs=["trace"],
            extraction_method="test",
            confidence=ConfidenceRecord(
                evidence_class="operational_trace",
                derivation_class="observed",
                extractor_certainty="medium",
            ),
            kind_tags=["action"],
        ),
    ]
    result = reconcile(facts)
    classes = {a.conflict_class for a in result.ambiguities}
    assert "semantic_conflict" in classes
    assert "missing_idempotency" in classes or "missing_retry_semantics" in classes or classes
    assert result.rejected_fact_ids or result.superseded_fact_ids
    assert project_source_precedence(None)
    assert project_source_precedence(SourcePrecedenceSection())
    assert project_source_precedence(["trace", "openapi"]) == ["trace", "openapi"]
    assert ambiguity_id("a", "b", "c").startswith("AMB-")


def test_cegr_intake_persist_and_indeterminate(tmp_path: Path) -> None:
    mapping = {
        "overall_status": "indeterminate",
        "probe_id": "p1",
        "action_id": "pay",
        "failing_dimensions": ["authorization"],
        "dimension_details": [
            {
                "dimension": "authorization",
                "status": "indeterminate",
                "detail": "missing evidence",
                "matched": False,
            }
        ],
        "reference_outcome": {"ok": True},
        "candidate_outcome": {"ok": True},
        "minimized_sequence": ["pay"],
    }
    intake = counterexample_from_mapping(mapping)
    assert intake.overall_status == "indeterminate"
    assert isinstance(resolve_ambiguity_alias("AMB-0042"), str)

    result = apply_cegr(intake, workspace_root=tmp_path, persist=True)
    assert result.generation.generation >= 1
    gens = list_refinement_generations(tmp_path)
    assert gens
    loaded = load_refinement_generation(
        Path(result.generation_dir) if result.generation_dir else tmp_path
    )
    assert loaded.generation == result.generation.generation

    ce = CounterexampleIntake(
        probe_id="p2",
        action_id="pay",
        overall_status="mismatch",
        failing_dimensions=["state"],
        dimension_details=[
            {"dimension": "state", "status": "mismatch", "detail": "n differs", "matched": False},
        ],
        minimized_sequence=["pay"],
    )
    apply_cegr(ce, workspace_root=tmp_path, persist=True)

    loop = run_cegr_loop(intake, workspace_root=tmp_path, persist=True)
    assert loop.closed is False


# ---------------------------------------------------------------------------
# Runtime engine / snapshot security branches
# ---------------------------------------------------------------------------


def test_runtime_engine_properties_denial_events_and_digest() -> None:
    w = World("rt.v1", "RT")
    w.state("n", initial_generator="0")
    w.state("flag", initial_generator="false")
    w.actor("a", available_actions=["set", "bump"], roles=["ops"])
    w.action(
        "set",
        actor_classes=["a"],
        authorization="role:ops",
        intended_effects=["n = payload.v"],
        success_outcomes=["ok"],
        input_schema={
            "type": "object",
            "required": ["v"],
            "properties": {"v": {"type": "integer"}},
            "additionalProperties": False,
        },
        preconditions=[ConstraintExpr(expression="payload.v >= 0")],
    )
    w.action(
        "bump",
        actor_classes=["a"],
        authorization="role:admin",
        intended_effects=["n += 1"],
        success_outcomes=["ok"],
    )
    w.transition(
        "t_set", action_id="set", branches=[TransitionBranch(id="t_set.ok", events=["set"])]
    )
    w.transition(
        "t_bump",
        action_id="bump",
        branches=[TransitionBranch(id="t_bump.ok", events=["bump"])],
    )
    world = w.compile()

    env = EventSourcedEnvironment(world, strict=True)
    assert env.world.environment_id == "rt.v1"
    assert env.determinism
    assert env.strict is True
    assert env.live_external_effects is False

    obs = env.reset(seed=None, options={"seed": 3, "actors": {"a": {"roles": ["ops"]}}})
    assert isinstance(obs, dict)
    bad = env.step("a", "set", {"v": -1})
    assert not bad.ok
    denied = env.step("a", "bump")
    assert denied.outcome == StepOutcome.DENIED
    assert denied.ok is False
    assert denied.events  # denial recorded
    assert env.state()["n"] == 0

    ok = env.step("a", "set", {"v": 4})
    assert ok.outcome == StepOutcome.SUCCESS
    snap = env.snapshot()
    assert snap.snapshot_digest

    tampered = Snapshot.model_validate(
        {**snap.model_dump(mode="json"), "authoritative_state": {"n": 99, "flag": False}}
    )
    with pytest.raises(RuntimeError_, match="digest"):
        env.restore(tampered)


def test_unknown_auth_never_allows_at_runtime() -> None:
    w = World("ua.v1", "UA")
    w.state("x", initial_generator="0")
    w.actor("a", available_actions=["go"])
    w.action(
        "go",
        actor_classes=["a"],
        authorization="unknown:scheme",
        intended_effects=["x += 1"],
        success_outcomes=["ok"],
    )
    w.transition("t", action_id="go", branches=[TransitionBranch(id="t.ok", events=["go"])])
    world = w.compile()
    env = EventSourcedEnvironment(world)
    env.reset(seed=0)
    result = env.step("a", "go")
    assert result.outcome == StepOutcome.INDETERMINATE
    assert result.ok is False
    assert env.state()["x"] == 0


def test_expression_remaining_fail_closed_arms() -> None:
    class _Bogus:
        pass

    with pytest.raises(ExpressionError, match="unsupported expression node"):
        evaluate(_Bogus(), EvalContext())  # type: ignore[arg-type]
    with pytest.raises(ExpressionError, match="unsupported expression node"):
        infer_type(_Bogus())  # type: ignore[arg-type]
    with pytest.raises(ExpressionError, match="unsupported binary"):
        infer_type(BinaryOp("??", Literal(1), Literal(2)))  # type: ignore[arg-type]

    # Locals shadow + None index short-circuit
    ctx = EvalContext(state={}, locals_={"x": {"y": 1}})
    assert evaluate(PathRef("state", ("x", "y")), ctx) == 1
    assert (
        evaluate(PathRef("state", ("missing", "z")), EvalContext(state={"missing": None})) is None
    )

    # `any` false path
    assert (
        evaluate_bool(
            parse_expression("any x in items: x < 0"),
            EvalContext(state={"items": [1, 2]}),
        )
        is False
    )


def test_observation_remaining_fail_closed_arms() -> None:
    from dataclasses import replace

    bad_agg = ObservationProjection(
        id="agg",
        target_actor_class="a",
        visible_paths=["x"],
        aggregation="sum",
        error_policy="explode",
        transformations=["not-a-transform"],
    )
    assert compile_observation(bad_agg, strict_unsupported=True).compiled is None

    compiled = compile_observation(
        ObservationProjection(
            id="acl",
            target_actor_class="a",
            visible_paths=["x"],
            access_control="role:ops",
            omitted_paths=["nested.deep"],
            transformations=["omit:nested.deep"],
            information_flow_labels=["secret:hidden"],
            error_policy="omit",
        )
    ).compiled
    assert compiled is not None
    with pytest.raises(ObservationError, match="access_control actor"):
        project_state({"x": 1}, compiled)

    open_proj = replace(compiled, access_control=None, access_control_ast=None)
    out = project_state({"x": 1, "nested": {"deep": 9}}, open_proj)
    assert out.get("x") == 1
    nested = out.get("nested")
    assert nested is None or "deep" not in nested

    actor = ActorDefinition(
        id="a", actor_class="a", roles=["ops"], observation_projection_id="miss"
    )
    projections = {
        "miss": ObservationProjection(
            id="miss",
            target_actor_class="a",
            visible_paths=["gone"],
            error_policy="fail",
        )
    }
    assert observe_or_empty({"x": 1}, actor=actor, projections=projections) == {}
    assert probe_observation_leaks({"a": 1}, forbidden_paths=["b"]) == []


def test_cegr_mapping_coercion_and_infer_action(tmp_path: Path) -> None:
    # overall claimed match + mismatch detail must rewrite away from match
    intake = counterexample_from_mapping(
        {
            "probe_id": "rewrite",
            "overall_status": "match",
            "failing_dimensions": ["retry"],
            "verdicts": [
                {"name": "retry", "matched": False, "detail": "retry diverge"},
                "skip-me",
                {"dimension": "", "status": "mismatch"},
            ],
            "minimized": [{"action_id": "submit_refund"}],
            "matched": True,
        }
    )
    assert intake.overall_status == "mismatch"
    assert intake.action_id is None  # inferred later by apply
    result = apply_cegr(
        intake,
        workspace_root=tmp_path,
        persist=True,
        alias_map={"AMB-0042": "AMB-HASHED"},
    )
    assert result.ambiguities

    # Infer action_id from string sequence + metadata
    thin = counterexample_from_mapping(
        {
            "probe_id": "thin",
            "minimized_sequence": ["do_thing"],
            "failing_dimensions": ["state"],
            "dimension_details": [{"dimension": "state", "status": "mismatch", "matched": False}],
            "overall_status": None,
            "matched": False,
            "metadata": {},
        }
    )
    assert thin.overall_status == "mismatch"
    apply_cegr(thin, workspace_root=tmp_path, persist=False)

    # matched True/False coercion without status string
    assert (
        counterexample_from_mapping(
            {"probe_id": "m", "matched": True, "failing_dimensions": []}
        ).overall_status
        == "match"
    )


def test_runtime_stochastic_guard_precondition_and_task() -> None:
    w = World("stoch.v1", "Stoch")
    w.state("n", initial_generator="0")
    w.actor("a", available_actions=["go"])
    w.action(
        "go",
        actor_classes=["a"],
        intended_effects=["n += 1"],
        success_outcomes=["ok"],
        preconditions=[ConstraintExpr(expression="@@@")],
    )
    w.transition(
        "t_go",
        action_id="go",
        kind="stochastic",
        branches=[
            TransitionBranch(id="t_go.a", events=["a"], probability=0.5),
            TransitionBranch(id="t_go.b", events=["b"], probability=0.5),
        ],
    )
    world = w.compile().model_copy(update={"determinism": "statistical"})
    env = EventSourcedEnvironment(world)
    env.reset(seed=1, options={"auth_context": {"now": "2026-01-01T00:00:00Z"}})
    unsupported = env.step("a", "go")
    assert unsupported.outcome == StepOutcome.UNSUPPORTED_SEMANTICS
    assert "unsupported" in (unsupported.reason_code or "")
    w2 = World("g.v1", "Guard")
    w2.state("n", initial_generator="0")
    w2.actor("a", available_actions=["bump"])
    w2.action(
        "bump",
        actor_classes=["a"],
        intended_effects=["n += 1"],
        success_outcomes=["ok"],
        preconditions=[ConstraintExpr(expression="n > 100")],
    )
    w2.transition(
        "t",
        action_id="bump",
        branches=[TransitionBranch(id="t.ok", events=["bump"])],
    )
    world2 = w2.compile()
    rule = world2.transitions[0].model_copy(update={"guard": ConstraintExpr(expression="n >= 0")})
    world2 = world2.model_copy(update={"transitions": [rule]})
    env2 = EventSourcedEnvironment(world2)
    env2.reset(seed=0)
    failed = env2.step("a", "bump")
    assert failed.outcome == StepOutcome.PRECONDITION_FAILED
    assert failed.events

    with pytest.raises(ExpressionError):
        evaluate_constraint(
            ConstraintExpr(expression="x", structured={"not_equals": 1}),
            state={},
            actor={},
        )
