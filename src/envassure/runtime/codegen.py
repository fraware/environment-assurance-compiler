"""Generate a simple deterministic Python runtime module from WorldDefinition."""

from __future__ import annotations

import json
from textwrap import dedent

from envassure.ir.models import WorldDefinition
from envassure.runtime.effects import coerce_literal


def generate_runtime_module(world: WorldDefinition) -> str:
    """Return source for a standalone module that applies event-derived writes.

    Transitions stage intended_effects into a write map, then commit by applying
    those writes (matching EventSourcedEnvironment event-sourced apply).
    """
    initial: dict[str, object] = {}
    for var in world.state:
        if var.initial_generator is not None:
            initial[var.id] = coerce_literal(var.initial_generator)
        elif var.type == "resource_counter":
            initial[var.id] = 0
        elif var.type == "enum" and var.enum_values:
            initial[var.id] = var.enum_values[0]
        else:
            initial[var.id] = None

    transitions: dict[str, list[str]] = {}
    for action in world.actions:
        transitions[action.id] = list(action.intended_effects)

    actors = {
        a.id: {
            "actor_class": a.actor_class,
            "available_actions": list(a.available_actions),
            "roles": list(a.roles),
        }
        for a in world.actors
    }

    initial_json = json.dumps(initial, sort_keys=True)
    transitions_json = json.dumps(transitions, sort_keys=True)
    actors_json = json.dumps(actors, sort_keys=True)

    body = dedent(
        f'''\
        """Generated EnvAssure runtime for {world.environment_id}.

        Event-derived deterministic apply: intended_effects produce writes,
        then writes are committed atomically (mirrors EventSourcedEnvironment).
        Do not edit by hand — regenerate from WorldDefinition.
        """

        from __future__ import annotations

        import copy
        import re
        from typing import Any

        ENVIRONMENT_ID = {world.environment_id!r}
        ENVIRONMENT_NAME = {world.name!r}
        DETERMINISM = {world.determinism!r}

        INITIAL_STATE: dict[str, Any] = {initial_json}

        # action_id -> intended_effect expressions
        TRANSITIONS: dict[str, list[str]] = {transitions_json}

        ACTORS: dict[str, dict[str, Any]] = {actors_json}

        _INCREMENT = re.compile(
            r"^\\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\\s*\\+=\\s*(?P<value>.+?)\\s*$"
        )
        _DECREMENT = re.compile(
            r"^\\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\\s*-=\\s*(?P<value>.+?)\\s*$"
        )
        _ASSIGN = re.compile(
            r"^\\s*(?P<name>[A-Za-z_][A-Za-z0-9_]*)\\s*=\\s*(?P<value>.+?)\\s*$"
        )


        def _literal(raw: str) -> Any:
            text = raw.strip()
            try:
                import ast

                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return text


        def stage_writes(state: dict[str, Any], expression: str) -> dict[str, Any]:
            """Stage one effect into a write map without mutating *state*."""
            working = copy.deepcopy(state)
            writes: dict[str, Any] = {{}}
            m = _INCREMENT.match(expression)
            if m:
                name = m.group("name")
                new_value = working.get(name, 0) + _literal(m.group("value"))
                writes[name] = new_value
                return writes
            m = _DECREMENT.match(expression)
            if m:
                name = m.group("name")
                new_value = working.get(name, 0) - _literal(m.group("value"))
                writes[name] = new_value
                return writes
            m = _ASSIGN.match(expression)
            if m:
                writes[m.group("name")] = _literal(m.group("value"))
                return writes
            raise ValueError(f"unsupported effect: {{expression!r}}")


        def apply_writes(state: dict[str, Any], writes: dict[str, Any]) -> dict[str, Any]:
            """Commit event-derived writes; returns new state."""
            next_state = copy.deepcopy(state)
            for key, value in writes.items():
                next_state[key] = copy.deepcopy(value)
            return next_state


        def apply_effect(state: dict[str, Any], expression: str) -> None:
            """Legacy in-place helper retained for compatibility."""
            writes = stage_writes(state, expression)
            state.update(writes)


        def initial_state() -> dict[str, Any]:
            return copy.deepcopy(INITIAL_STATE)


        def apply_action(state: dict[str, Any], action_id: str) -> dict[str, Any]:
            """Stage intended_effects then commit writes (event-sourced apply)."""
            effects = TRANSITIONS.get(action_id)
            if effects is None:
                raise KeyError(f"unknown action {{action_id!r}}")
            write_map: dict[str, Any] = {{}}
            working = copy.deepcopy(state)
            for expression in effects:
                write_map.update(stage_writes(working, expression))
                working.update(write_map)
            return apply_writes(state, write_map)


        def step_sequence(
            actions: list[str],
            *,
            start: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            state = initial_state() if start is None else copy.deepcopy(start)
            for action_id in actions:
                state = apply_action(state, action_id)
            return state
        '''
    )
    return body


def write_runtime_module(world: WorldDefinition, path: str) -> str:
    """Write generated module to *path*; return the source text."""
    source = generate_runtime_module(world)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(source)
    return source
