"""Tests for canonical JSON encoding and hashing."""

from __future__ import annotations

import pytest

from envassure.canonical import (
    CanonicalJsonError,
    canonical_dumps,
    canonical_hash,
)


def test_object_key_order_independent() -> None:
    a = {"b": 1, "a": 2}
    b = {"a": 2, "b": 1}
    assert canonical_dumps(a) == canonical_dumps(b) == '{"a":2,"b":1}'
    assert canonical_hash(a) == canonical_hash(b)


def test_primitives() -> None:
    assert canonical_dumps(None) == "null"
    assert canonical_dumps(True) == "true"
    assert canonical_dumps(False) == "false"
    assert canonical_dumps(0) == "0"
    assert canonical_dumps("hi") == '"hi"'
    assert canonical_dumps([1, "x", None]) == '[1,"x",null]'


def test_string_escaping() -> None:
    assert canonical_dumps('a"b\\c') == '"a\\"b\\\\c"'
    assert canonical_dumps("line\n") == '"line\\n"'


def test_nested_stable_hash() -> None:
    payload = {
        "sources": [{"id": "a", "digest": "abc"}, {"id": "b", "digest": "def"}],
        "meta": {"v": 1},
    }
    digest = canonical_hash(payload)
    assert len(digest) == 64
    assert digest == canonical_hash(
        {
            "meta": {"v": 1},
            "sources": [{"id": "a", "digest": "abc"}, {"id": "b", "digest": "def"}],
        }
    )


def test_rejects_non_string_keys() -> None:
    with pytest.raises(CanonicalJsonError):
        canonical_dumps({1: "x"})  # type: ignore[dict-item]


def test_rejects_nan() -> None:
    with pytest.raises(CanonicalJsonError):
        canonical_dumps(float("nan"))


def test_negative_zero_normalizes() -> None:
    assert canonical_dumps(-0.0) == "0"
