# Validation and fidelity

Fidelity is a **multi-dimensional profile**, not a single score
([ADR-0005](https://github.com/fraware/environment-assurance-compiler/blob/main/adrs/0005-fidelity-profile.md)).

## What build success means

Successfully running `eac build-ir`, `eac lint`, or `eac package` means the
artifacts are well-formed and locked enough to inspect. It does **not** mean:

- behavioral parity with a production system
- complete timeout / retry / auth coverage
- that open ambiguities are acceptable for your release bar

## Evidence dimensions (examples)

| Kind | Typical commands / artifacts |
| ---- | ---------------------------- |
| Static structure | `eac lint`, `eac analyze` (`EAC3xxx`–`EAC5xxx`) |
| Dynamic / determinism | `eac run`, `eac replay`, `eac test` |
| Differential | `eac differential` with fixtures / simulators (`EAC7xxx`) |
| Coverage / mutation | `eac coverage`, mutation helpers in the analysis package |
| Decisions | closed ambiguities + provenance |
| Pack integrity | `eac verify-pack` (`EAC8006`) |

Declared levels such as `EF-0`…`EF-5` on a world are **claims** that must be
backed by artifacts in the assurance report (`eac report`), not grades assigned
by a leaderboard.

## Honest scoping

Prefer recorded fixtures and file-backed simulators in CI. Network and subprocess
connectors are opt-in and do not by themselves prove fidelity. See
[Differentially validate](../guides/differentially-validate.md),
[Fidelity claims](../guides/fidelity-claims.md), and
[Limitations](../research/limitations.md).
