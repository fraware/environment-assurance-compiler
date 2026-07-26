# Maintainers

This file lists people and GitHub identities responsible for EnvAssure
(`envassure` / `eac`) releases, security triage, and repository administration.

Keep [`.github/CODEOWNERS`](.github/CODEOWNERS) synchronized with this list.

## Active maintainers

| Name | GitHub | Role | Keys / notes |
| ---- | ------ | ---- | ------------ |
| fraware | [@fraware](https://github.com/fraware) | Primary maintainer | Release tags must be annotated and signed with a key registered for this identity (see release-process). |

Update this table when maintainers join or leave. Do not leave orphaned
CODEOWNERS entries.

## Responsibilities

- Review and merge PRs to `main` (security-critical paths: **two** approving
  reviews — see [`CONTRIBUTING.md`](CONTRIBUTING.md)).
- Cut signed annotated `v*` tags and drive the Release workflow.
- Triage security reports per [`SECURITY.md`](SECURITY.md).
- Own GitHub Environments (`testpypi`, `pypi`, `github-pages`, `ghcr`) and
  PyPI / TestPyPI trusted-publisher configuration.
- Refresh digest-pinned container base images when rebuilding GHCR images.

## Emeritus

_None yet._

## Becoming a maintainer

Maintainer status is granted by existing maintainers after sustained,
high-quality contribution and agreement to the DCO and security policy.
Document the change here and in CODEOWNERS in the same PR.
