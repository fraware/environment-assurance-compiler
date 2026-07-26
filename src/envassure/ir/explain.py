"""Explain IR elements via provenance links."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from envassure.ir.models import WorldDefinition


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    element_kind: str
    element_id: str
    summary: str
    source_ids: list[str] = Field(default_factory=list)
    decision_ids: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)
    origin_kind: str | None = None
    related: list[str] = Field(default_factory=list)
    notes: str | None = None


def explain_element(world: WorldDefinition, element_id: str) -> Explanation | None:
    """Trace an IR element id to provenance and related artifacts."""
    for state in world.state:
        if state.id == element_id:
            return Explanation(
                element_kind="state",
                element_id=element_id,
                summary=f"State variable {state.name} ({state.type})",
                source_ids=state.provenance.source_ids,
                decision_ids=state.provenance.decision_ids,
                fact_ids=state.provenance.fact_ids,
                origin_kind=state.provenance.origin_kind,
                notes=state.provenance.notes,
            )
    for action in world.actions:
        if action.id == element_id:
            related = [f"transition:{t.id}" for t in world.transitions if t.action_id == action.id]
            return Explanation(
                element_kind="action",
                element_id=element_id,
                summary=f"Action contract {action.id} v{action.version}",
                source_ids=action.provenance.source_ids,
                decision_ids=action.provenance.decision_ids,
                fact_ids=action.provenance.fact_ids,
                origin_kind=action.provenance.origin_kind,
                related=related,
                notes=action.provenance.notes,
            )
    for transition in world.transitions:
        if transition.id == element_id:
            return Explanation(
                element_kind="transition",
                element_id=element_id,
                summary=f"Transition for action {transition.action_id}",
                source_ids=transition.provenance.source_ids,
                decision_ids=transition.provenance.decision_ids,
                fact_ids=transition.provenance.fact_ids,
                origin_kind=transition.provenance.origin_kind,
                related=[f"action:{transition.action_id}"],
                notes=transition.provenance.notes,
            )
    for verifier in world.verifiers:
        if verifier.id == element_id:
            return Explanation(
                element_kind="verifier",
                element_id=element_id,
                summary=verifier.statement,
                source_ids=verifier.provenance.source_ids,
                decision_ids=verifier.provenance.decision_ids,
                fact_ids=verifier.provenance.fact_ids,
                origin_kind=verifier.provenance.origin_kind,
                notes=verifier.provenance.notes,
            )
    for ambiguity in world.ambiguities:
        if ambiguity.id == element_id:
            return Explanation(
                element_kind="ambiguity",
                element_id=element_id,
                summary=ambiguity.subject,
                source_ids=ambiguity.provenance.source_ids,
                decision_ids=[ambiguity.decision_id] if ambiguity.decision_id else [],
                origin_kind=ambiguity.provenance.origin_kind,
                related=[f"action:{a}" for a in ambiguity.affected_actions],
                notes=ambiguity.residual_uncertainty,
            )
    for actor in world.actors:
        if actor.id == element_id:
            return Explanation(
                element_kind="actor",
                element_id=element_id,
                summary=f"Actor {actor.actor_class}",
                source_ids=actor.provenance.source_ids,
                decision_ids=actor.provenance.decision_ids,
                fact_ids=actor.provenance.fact_ids,
                origin_kind=actor.provenance.origin_kind,
                related=[f"action:{a}" for a in actor.available_actions],
            )
    return None
