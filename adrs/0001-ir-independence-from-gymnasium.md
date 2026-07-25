# ADR-0001: IR Independence from Gymnasium

- Status: Accepted
- Date: 2026-07-25

## Context

Many environment toolkits bind the world model to a single execution framework
(Gymnasium, PettingZoo, proprietary simulators). EnvAssure must support multiple
evaluation frameworks and remain useful for static analysis and packaging without
a live gym loop.

## Decision

The Environment Assurance IR is framework-agnostic. Gymnasium and PettingZoo
adapters are optional extras (`[gym]`, `[pettingzoo]`) with lazy imports. Core
IR, validation, and pack format must not import those libraries.

## Consequences

- Reference runtime implements an EnvAssure-native protocol first.
- Adapters translate IR/runtime to Gymnasium/PettingZoo APIs.
- CI core matrix does not require gym extras.
- Missing extras fail closed with `EAC9003` when those features are requested.
