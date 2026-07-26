---
name: Bug report
about: Unexpected compiler, runtime, CLI, or documentation behavior
title: "[bug] "
labels: bug
assignees: ""
---

## Summary

A clear description of what went wrong.

## Environment

- OS:
- Python version:
- `envassure` / commit (`git rev-parse HEAD` or PyPI version):
- Install method (`pip install -e .`, wheel, etc.):

## Steps to reproduce

1.
2.
3.

## Expected

## Actual

Include exit codes, diagnostics (`EAC####`), and `--json` output when useful.

## Artifacts

Attach or link minimal IR / workspace snippets (redact secrets). Do **not**
upload packs that may contain sensitive operational data without scrubbing.

## Notes

Is this an **environment fidelity** defect (world vs production) rather than a
compiler bug? Prefer the “Environment defect” template and
[report-environment-defect](https://github.com/fraware/environment-assurance-compiler/blob/main/docs/guides/report-environment-defect.md).
