# ADR-0005: Fidelity Profile (No Single Score)

- Status: Accepted
- Date: 2026-07-25

## Context

A single fidelity number encourages gaming and hides asymmetric gaps (for
example strong schema match with weak timeout semantics).

## Decision

Fidelity is a multi-dimensional profile (EF-0…EF-5 and categorical evidence), not
a composite leaderboard score. Build success does not imply fidelity evidence.
Assurance reports surface dimensions separately.

## Consequences

- No default ranking of packs by a scalar.
- Release criteria cite required dimensions per use case.
- Differential and static analyses feed the profile, not a single grade.
- Documentation and CLI must avoid overclaiming parity with production systems.
