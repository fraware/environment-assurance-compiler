# Exit codes

Stable process exit codes for `eac`. Automation should rely on these values,
not on parsing human text. Prefer `--json` for structured results.

| Code | Name           | Meaning                                                      |
| ---- | -------------- | ------------------------------------------------------------ |
| 0    | SUCCESS        | Command completed with no blocking diagnostics.              |
| 1    | ERROR          | Blocking diagnostics or general command failure.             |
| 2    | USAGE          | Invalid CLI usage or argument parsing failure.               |
| 3    | UNIMPLEMENTED  | Registered command not yet implemented (fail-closed).        |
| 4    | WORKSPACE      | Workspace missing, invalid, or lock inconsistency.           |
| 5    | DOCTOR         | Doctor checks failed (non-workspace toolchain errors).       |
| 99   | INTERNAL       | Unexpected internal error.                                   |

Source of truth: `envassure.diagnostics.exit_codes.ExitCode`.
