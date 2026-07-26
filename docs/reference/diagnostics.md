# Diagnostics

Every shipped diagnostic code is registered in
`envassure.diagnostics.catalog.DIAGNOSTIC_CATALOG` and must include documentation
from day one. This page mirrors the catalog; the Python module is the source of
truth if they ever diverge.

## Code freeze policy

Diagnostic codes are **semantically frozen** once shipped:

1. Every emitted code must appear in `DIAGNOSTIC_CATALOG` (enforced by
   `require_documented` and the catalog coverage unit test).
2. Reusing an existing code for different severity, summary meaning,
   documentation, consequence, suggested repair, or `claim_impact` is forbidden
   without an intentional catalog revision that updates the golden semantic
   fingerprint (`tests/fixtures/diagnostics/catalog_semantic_fingerprint.txt`).
3. Prefer minting a new code over silently changing the meaning of an old one.
4. `summary` explains the issue; `claim_impact` (when present) states which
   fidelity/assurance claim is weakened; `suggested_repair` remains the
   remediation hint; `source_refs` / `SourceRef` remain the location carrier.

## Families

| Family | Concern |
| ------ | ------- |
| EAC1xxx | Source ingestion |
| EAC2xxx | Semantic conflicts |
| EAC3xxx | IR validation and migrate |
| EAC4xxx | State and transition analysis |
| EAC5xxx | Observation and information flow |
| EAC6xxx | Task and verifier generation |
| EAC7xxx | Differential validation / CEGR |
| EAC8xxx | Packaging, workspace, lock, reproducibility |
| EAC9xxx | Plugin, CLI, compatibility, toolchain |

## Severity

| Severity | Meaning |
| -------- | ------- |
| `error` | Blocks the command |
| `warning` | Soft issue; may block release builds later |
| `note` | Explains derived or skipped behavior |
| `help` | Suggests a command or edit |

Use `eac <cmd> --json` for structured diagnostic objects. Structured objects may
include optional `claim_impact`.

## Catalog

### EAC1xxx — Source ingestion

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC1001 | error | Invalid `SourceArtifact` |
| EAC1002 | error | Unknown authority class |
| EAC1003 | warning | Completeness declaration note |
| EAC1004 | error | Failed to parse source artifact |
| EAC1005 | error | Unknown source adapter kind |
| EAC1006 | warning | Unsupported source feature outside adapter matrix |

### EAC2xxx — Semantic conflicts

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC2001 | warning | Open ambiguity remains unresolved |
| EAC2002 | error | Semantic conflict requiring a decision |
| EAC2003 | warning | Alias detected between subjects |
| EAC2004 | error | Unknown or closed ambiguity on decide |

### EAC3xxx — IR validation / migrate

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC3001 | error | Invalid world definition |
| EAC3002 | error | Broken IR reference |
| EAC3003 | error | Duplicate IR identifier |
| EAC3004 | error | Unsupported IR version |
| EAC3005 | note | IR migrate status (including no-op) |
| EAC3006 | error | IR migrate transform failure |
| EAC3007 | error | Release readiness gate failure |
| EAC3008 | error | Provenance origin_kind conflict |

### EAC4xxx — State and transition analysis

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC4001 | error | Transition analysis failure |
| EAC4002 | warning | Reachability / solvability issue |
| EAC4003 | warning | Reset integrity issue |
| EAC4004 | error | Authority / delegation issue |
| EAC4005 | note | Resource conservation hint |
| EAC4006 | warning | Transaction / retry consistency |
| EAC4007 | warning | Termination integrity |
| EAC4008 | error | Mutation scope violation |
| EAC4009 | warning | Unreachable action |
| EAC4010 | error | Precondition / guard reference issue |
| EAC4027 | error | Retry semantics undefined (timeout without retry) |

### EAC5xxx — Observation / information flow

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC5001 | error | Observation / information-flow issue |
| EAC5002 | error | Evaluator-visible state leaked into policy observation |
| EAC5003 | warning | Declared information-flow mapping issue |

### EAC6xxx — Tasks / verifiers

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC6001 | warning | Task / verifier generation note |
| EAC6002 | error | Hidden-oracle leakage in verifier |
| EAC6003 | note | Solve–verify asymmetry |

### EAC7xxx — Differential / CEGR

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC7001 | error | Differential validation failure |
| EAC7002 | note | Stochastic comparison uses statistical conformance |
| EAC7003 | warning | Counterexample minimized |
| EAC7004 | warning | CEGR intake skipped proposals |
| EAC7005 | note | CEGR refinement applied |

### EAC8xxx — Workspace / packaging

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC8001 | error | Not an EnvAssure workspace |
| EAC8002 | error | Workspace already exists |
| EAC8003 | error | Invalid workspace configuration |
| EAC8004 | error | Lock inconsistency |
| EAC8005 | error | Failed to write workspace file |
| EAC8006 | error | Pack verification failed |
| EAC8007 | note | Incremental rebuild skipped |
| EAC8008 | note | Incremental lint skipped |

### EAC9xxx — Toolchain / plugins

| Code | Severity | Summary |
| ---- | -------- | ------- |
| EAC9001 | error | Command not implemented (fail-closed stub) |
| EAC9002 | error | Unsupported Python version |
| EAC9003 | warning | Optional extra missing |
| EAC9004 | note | Network checks skipped |
| EAC9005 | error | Internal error |
| EAC9006 | error | Plugin error (load / API / allowlist) |
| EAC9007 | error | Runtime replay/assurance failure |

## Related

- [Exit codes](exit-codes.md)
- [CLI](cli.md)
