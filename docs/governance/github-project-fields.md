# GitHub Project field template

Ops creates the public GitHub Project board. This document is the **field and
view contract** so roadmap issues stay comparable. Do not treat the board as a
calendar; owners and acceptance tests are mandatory before dates appear.

Companion machine-readable sketch:
[`.github/project-fields.yml`](https://github.com/fraware/environment-assurance-compiler/blob/main/.github/project-fields.yml).

## Project purpose

Track engineering work for EnvAssure (`envassure` / `eac`) across the buckets in
[`ROADMAP.md`](https://github.com/fraware/environment-assurance-compiler/blob/main/ROADMAP.md): Now / Next / Research / Later / Declined.

Out of scope for the board:

- Grant funding, selection, or payment status
- Private security advisories (use GitHub Security Advisories)
- Auto-install plugin marketplace workflows

## Required custom fields

Create these Project fields (names are normative for filters):

| Field | Type | Values / format |
| ----- | ---- | --------------- |
| `Roadmap bucket` | Single select | `Now`, `Next`, `Research`, `Later`, `Declined` |
| `Problem` | Text | One-paragraph problem statement |
| `Intended claim` | Text | What may be asserted after merge; call out non-claims |
| `Deliverable` | Text | Artifact list (paths, workflows, packs) |
| `Owner` | Text | GitHub handle or `CODEOWNERS` path |
| `Dependencies` | Text | Issue URLs or “none” |
| `Acceptance test` | Text | Exact commands / CI job names |
| `Compatibility impact` | Single select | `none`, `docs-only`, `cli`, `ir`, `plugin-api`, `pack-format`, `breaking` |
| `Status` | Single select | `proposed`, `accepted`, `in_progress`, `blocked`, `done`, `declined` |
| `Milestone train` | Single select | `A-release`, `B-docs`, `C-integrations`, `D-research`, `E-community`, `post-beta` |

Optional fields:

| Field | Type | Notes |
| ----- | ---- | ----- |
| `Area` | Single select | `docs`, `runtime`, `packaging`, `integrations`, `benchmarks`, `security`, `governance` |
| `Good first` | Iteration / checkbox | Link to drafts under `docs/community/good-first-issues/` |
| `Target version` | Text | e.g. `0.2.0b1`, `0.2.0`, `unscheduled` |

## Issue body checklist

Issues linked from the Project should include the same headings:

```markdown
## Problem
## Intended claim
## Deliverable
## Owner
## Dependencies
## Acceptance test
## Compatibility impact
## Status
```

## Suggested views

1. **Board by Status** — columns = `Status`; swimlanes optional by `Area`.
2. **Roadmap table** — group by `Roadmap bucket`; sort by `Status`.
3. **Beta gate** — filter `Milestone train` in {A,B,C,D,E} and `Status` ≠ `done`.
4. **Declined archive** — filter `Roadmap bucket` = `Declined`.

## Ops checklist (maintainers)

- [ ] Create public Project linked to this repository
- [ ] Add fields above with the listed option sets
- [ ] Add default views
- [ ] Document Project URL in `ROADMAP.md` when live
- [ ] Do not add funding or payment custom fields

## Related

- [ROADMAP.md](https://github.com/fraware/environment-assurance-compiler/blob/main/ROADMAP.md)
- [Governance index](index.md)
