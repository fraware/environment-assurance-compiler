"""Manual Python authoring SDK for Environment Assurance IR."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from envassure.ir.models import (
    ActionContract,
    ActorDefinition,
    FailureDefinition,
    ObservationProjection,
    StateVariable,
    TaskTemplate,
    TransitionBranch,
    TransitionRule,
    VerifierClaim,
    WorldDefinition,
)
from envassure.ir.primitives import (
    ConstraintExpr,
    FailureCategory,
    OriginKind,
    ProvenanceRef,
    StateTypeName,
)


class World:
    """Builder for a WorldDefinition via a fluent / decorator-friendly API."""

    def __init__(
        self,
        environment_id: str,
        name: str,
        *,
        version: str = "0.1.0",
        description: str = "",
        domain: str = "generic",
    ) -> None:
        self._world = WorldDefinition(
            environment_id=environment_id,
            name=name,
            version=version,
            description=description,
            domain=domain,
        )

    @property
    def definition(self) -> WorldDefinition:
        return self._world

    def state(
        self,
        id: str,
        *,
        name: str | None = None,
        type: StateTypeName = "scalar",
        **kwargs: Any,
    ) -> StateVariable:
        var = StateVariable(id=id, name=name or id, type=type, **kwargs)
        self._world.state.append(var)
        return var

    def actor(
        self,
        id: str,
        *,
        actor_class: str | None = None,
        **kwargs: Any,
    ) -> ActorDefinition:
        actor = ActorDefinition(id=id, actor_class=actor_class or id, **kwargs)
        self._world.actors.append(actor)
        return actor

    def observation(
        self, id: str, *, target_actor_class: str, **kwargs: Any
    ) -> ObservationProjection:
        obs = ObservationProjection(id=id, target_actor_class=target_actor_class, **kwargs)
        self._world.observations.append(obs)
        return obs

    def action(
        self,
        id: str,
        *,
        actor_classes: list[str] | None = None,
        **kwargs: Any,
    ) -> ActionContract:
        action = ActionContract(id=id, actor_classes=actor_classes or [], **kwargs)
        self._world.actions.append(action)
        return action

    def failure(
        self,
        id: str,
        *,
        category: FailureCategory,
        description: str,
        **kwargs: Any,
    ) -> FailureDefinition:
        failure = FailureDefinition(id=id, category=category, description=description, **kwargs)
        self._world.failures.append(failure)
        return failure

    def transition(
        self,
        id: str,
        *,
        action_id: str,
        events: list[str] | None = None,
        kind: str = "deterministic",
        **kwargs: Any,
    ) -> TransitionRule:
        branches = kwargs.pop("branches", None)
        if branches is None:
            branches = [TransitionBranch(id=f"{id}.ok", events=events or [f"{action_id}.applied"])]
        rule = TransitionRule(
            id=id,
            action_id=action_id,
            kind=kind,  # type: ignore[arg-type]
            branches=branches,
            **kwargs,
        )
        self._world.transitions.append(rule)
        return rule

    def task(self, id: str, *, family: str, intent: str, **kwargs: Any) -> TaskTemplate:
        task = TaskTemplate(id=id, family=family, intent=intent, **kwargs)
        self._world.tasks.append(task)
        return task

    def verifier(
        self,
        id: str,
        *,
        statement: str,
        decision_rule: str,
        **kwargs: Any,
    ) -> VerifierClaim:
        claim = VerifierClaim(id=id, statement=statement, decision_rule=decision_rule, **kwargs)
        self._world.verifiers.append(claim)
        return claim

    def compile(self) -> WorldDefinition:
        """Return the IR document (same shape import adapters will produce)."""
        return self._world.model_copy(deep=True)


def state(id: str, **kwargs: Any) -> Callable[[World], StateVariable]:
    def apply(world: World) -> StateVariable:
        return world.state(id, **kwargs)

    return apply


def actor(id: str, **kwargs: Any) -> Callable[[World], ActorDefinition]:
    def apply(world: World) -> ActorDefinition:
        return world.actor(id, **kwargs)

    return apply


def action(id: str, **kwargs: Any) -> Callable[[World], ActionContract]:
    def apply(world: World) -> ActionContract:
        return world.action(id, **kwargs)

    return apply


def task(id: str, **kwargs: Any) -> Callable[[World], TaskTemplate]:
    def apply(world: World) -> TaskTemplate:
        return world.task(id, **kwargs)

    return apply


def constraint(expression: str) -> ConstraintExpr:
    return ConstraintExpr(expression=expression)


def provenance(
    *,
    source_ids: list[str] | None = None,
    decision_ids: list[str] | None = None,
    fact_ids: list[str] | None = None,
    origin_kind: OriginKind | None = None,
    notes: str | None = None,
) -> ProvenanceRef:
    return ProvenanceRef(
        source_ids=source_ids or [],
        decision_ids=decision_ids or [],
        fact_ids=fact_ids or [],
        origin_kind=origin_kind,
        notes=notes,
    )
