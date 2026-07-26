# GFI-08: Shell-completion docs

## Problem

CLI users need documented shell completion setup (`eac` / Typer / Click
completion, as applicable) without digging through framework docs.

## Intended claim

Docs explain how to install bash/zsh/fish (and PowerShell if supported)
completions for `eac`. Does **not** claim completions cover every dynamic
argument.

## Deliverable

- Section in `docs/reference/cli.md` or `docs/getting-started.md`
- Commands tested manually on at least one Unix shell; note Windows status
- Link from contributing development page

## Files

- `docs/reference/cli.md`
- `docs/getting-started.md` (optional short pointer)
- `docs/contributing/development.md` (optional)
- No production code changes required unless completion entry points are missing

## Tests

- Docs build (`mkdocs build --strict`) still passes
- Snippet commands match `eac --help` / framework completion invocation
- Optional: smoke script that runs completion generation into a temp file

## Non-goals

- Replacing the CLI framework
- Full argument graph fuzzing
- Changing exit codes or diagnostics catalog
- Auth / snapshot work

## Reviewer

CLI / docs area owner (`CODEOWNERS` for `docs/reference/cli.md`, `src/envassure/cli/`).

## Status

`proposed` — good first issue
