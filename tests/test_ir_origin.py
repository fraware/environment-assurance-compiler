"""Tests for ProvenanceRef.origin_kind and derivation compatibility."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from envassure import World
from envassure.api import provenance
from envassure.ir.models import AmbiguityRecord, WorldDefinition
from envassure.ir.primitives import (
    ProvenanceRef,
    origin_kind_conflict_reason,
    origin_kind_for_derivation,
    validate_provenance_origin,
)
from envassure.ir.validate import validate_world


def test_origin_kind_for_derivation_mapping() -> None:
    assert origin_kind_for_derivation("direct") == "source_derived"
    assert origin_kind_for_derivation("observed") == "source_derived"
    assert origin_kind_for_derivation("inferred") == "inferred"
    assert origin_kind_for_derivation("expert") == "human_decision"


def test_inferred_cannot_be_source_derived() -> None:
    reason = origin_kind_conflict_reason("source_derived", ["inferred"])
    assert reason is not None
    assert "inferred" in reason
    assert validate_provenance_origin(
        ProvenanceRef(origin_kind="source_derived", notes="derivation_class=inferred"),
        derivation_classes=["inferred"],
        subject="action:submit_refund",
    )


def test_direct_source_derived_ok() -> None:
    assert origin_kind_conflict_reason("source_derived", ["direct"]) is None
    assert (
        validate_provenance_origin(
            ProvenanceRef(origin_kind="source_derived"),
            derivation_classes=["direct"],
        )
        is None
    )


def test_provenance_ref_rejects_unknown_origin_kind() -> None:
    with pytest.raises(ValidationError):
        ProvenanceRef(origin_kind="made_up")  # type: ignore[arg-type]


def test_sdk_provenance_accepts_origin_kind() -> None:
    ref = provenance(source_ids=["manual"], origin_kind="human_decision", notes="authored")
    assert ref.origin_kind == "human_decision"


def test_pipeline_rejects_inferred_tagged_source_derived() -> None:
    world = World("x", "X")
    world.state("s")
    world.actor("a", available_actions=["act"])
    world.action("act", actor_classes=["a"])
    world.transition("t", action_id="act")
    compiled = world.compile()
    compiled.actions[0].provenance = ProvenanceRef(
        origin_kind="source_derived",
        notes="derivation_class=inferred",
    )
    report = validate_world(compiled)
    assert any(d.code == "EAC3008" for d in report.diagnostics)


def test_pipeline_rejects_open_ambiguity_source_derived() -> None:
    world = WorldDefinition(
        environment_id="demo",
        name="Demo",
        ambiguities=[
            AmbiguityRecord(
                id="AMB-1",
                subject="action:x",
                conflict_class="semantic_conflict",
                status="open",
                default_prohibition="Do not project without a decision.",
                operational_consequence="IR incomplete for subject.",
                required_expert_role="domain_expert",
                provenance=ProvenanceRef(origin_kind="source_derived"),
            )
        ],
    )
    report = validate_world(world)
    assert any(d.code == "EAC3008" for d in report.diagnostics)
