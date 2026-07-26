# GFI-03: Gymnasium enum codec tests

## Problem

Gymnasium adapter codecs for enum / categorical action and observation spaces
need explicit round-trip and fail-closed tests so contributors can extend spaces
without breaking registration.

## Intended claim

Enum codec encode/decode is covered by tests including malformed values.
Does **not** claim PettingZoo conformance or RL trainer integration.

## Deliverable

- Parametrized tests for enum (and adjacent categorical) codecs used by
  `gymnasium_env` / `runtime/adapters/common.py`
- Failure cases: unknown member, wrong type, empty enum
- Brief comment or docs note pointing to the test module

## Files

- `src/envassure/runtime/adapters/gymnasium_env.py`
- `src/envassure/runtime/adapters/common.py`
- `tests/runtime/adapters/test_gymnasium_enum_codec.py` (new or extend existing)
- Optional: `docs/integrations/gymnasium.md` (link to test expectations only)

## Tests

- Round-trip for a small enum space
- `check_env` still passes for a minimal deterministic world using enums (if
  gym extra installed; skip otherwise with clear marker)
- Malformed action → fail closed (no silent coerce)

## Non-goals

- Redesigning reward providers
- PettingZoo qualification
- Payload `Dict` space redesign beyond enums
- Authorization / snapshot work

## Reviewer

Runtime adapters area owner (`CODEOWNERS` for `src/envassure/runtime/adapters/`).

## Status

`proposed` — good first issue
