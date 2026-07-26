"""EAC-07: fidelity ledger schema, no-score guard, report wiring."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from envassure.fidelity import (
    ClaimScope,
    FidelityClaim,
    FidelityLedger,
    average_fidelity_score,
    composite_fidelity_score,
    ledger_from_world,
    mean_fidelity,
)
from envassure.reports import build_assurance_case


def _load_example(name: str):
    root = Path(__file__).resolve().parents[1] / "examples" / name / "world.py"
    spec = importlib.util.spec_from_file_location(f"ex_{name}", root)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fidelity_claim_requires_scope_and_gaps_below_expert() -> None:
    with pytest.raises(ValidationError):
        ClaimScope(environment_id="env", element_ids=[], dimension=None)

    with pytest.raises(ValidationError, match="known_gaps"):
        FidelityClaim(
            claim="Schema only",
            scope=ClaimScope(environment_id="env", dimension="schema"),
            status="structurally_valid",
            known_gaps=[],
        )

    claim = FidelityClaim(
        claim="Reviewed auth path",
        scope=ClaimScope(environment_id="env", element_ids=["action:approve"]),
        status="expert_reviewed",
        evidence=["decision:dec-1"],
        coverage="auth fixture set A",
        reviewer="alice",
        known_gaps=[],
    )
    assert claim.status == "expert_reviewed"


def test_ledger_rejects_score_metadata_and_averaging_apis() -> None:
    with pytest.raises(ValidationError, match="aggregate score"):
        FidelityLedger(
            environment_id="env",
            claims=[],
            metadata={"aggregate_score": 0.9},
        )

    for fn in (average_fidelity_score, mean_fidelity, composite_fidelity_score):
        with pytest.raises(ValueError, match="forbidden"):
            fn([0.1, 0.9])


def test_assurance_case_sections_use_ledger() -> None:
    world = _load_example("counter").build_counter_world()
    ledger = FidelityLedger(
        environment_id=world.environment_id,
        claims=[
            FidelityClaim(
                claim="Counter increment is structurally valid under lint.",
                scope=ClaimScope(
                    environment_id=world.environment_id,
                    element_ids=["action:increment"],
                    dimension="schema",
                ),
                evidence=["lint:clean"],
                coverage="counter example",
                known_gaps=["No differential oracle attached."],
                status="structurally_valid",
            )
        ],
    )
    case = build_assurance_case(world, fidelity_ledger=ledger, generated_at="2026-01-01T00:00:00Z")
    assert case.fidelity_ledger is not None
    assert case.fidelity_ledger.content_digest() == ledger.content_digest()
    sec_203 = case.section("20.3")
    sec_204 = case.section("20.4")
    assert sec_203 is not None and "ledger" in " ".join(sec_203.body).lower()
    assert sec_204 is not None
    assert any(t.get("caption") == "Fidelity ledger claims" for t in sec_204.tables)
    assert "fidelity_ledger" in case.artifacts
    assert "score" not in case.metadata
    assert "aggregate_score" not in case.model_dump(mode="json")


def test_ledger_from_world_seeds_structurally_valid() -> None:
    world = _load_example("counter").build_counter_world()
    ledger = ledger_from_world(world)
    assert ledger.environment_id == world.environment_id
    assert len(ledger.claims) == 1
    assert ledger.claims[0].status == "structurally_valid"
    assert ledger.claims[0].known_gaps
