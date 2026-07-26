---
name: Environment defect
about: Fidelity / semantics gap between an EnvAssure world and a real system
title: "[env-defect] "
labels: environment-defect
assignees: ""
---

## Summary

What operational behavior is missing, wrong, or under-specified in the world?

## Systems under comparison

- Production / reference system (name, version, surface):
- EnvAssure environment id / IR path:
- Declared fidelity level / assurance profile (if any):

## Evidence class

- [ ] Direct (spec, code, observed logs)
- [ ] Observed (traces, differential probes)
- [ ] Inferred (reasonable but not proven)
- [ ] Expert judgment (decision id / rationale)

Link artifacts: facts, ambiguities, differential reports, CEGR intake, packs.

## Minimal probe or scenario

Describe the failing action sequence, actors, payloads, and expected vs actual
outcomes. Prefer offline fixtures over live systems.

## Impact

Which claims become unsafe if this defect remains open?

## Related

Follow [How to report an environment defect](https://github.com/fraware/environment-assurance-compiler/blob/main/docs/guides/report-environment-defect.md).
Security issues: private disclosure via [SECURITY.md](https://github.com/fraware/environment-assurance-compiler/blob/main/SECURITY.md) — do not file here.
