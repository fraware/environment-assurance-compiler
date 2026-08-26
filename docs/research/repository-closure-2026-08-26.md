# Repository closure record — 2026-08-26

This document records the final repository-administration pass for EnvAssure on
2026-08-26. It is an audit record, not a new scientific or release-readiness
claim. Where this document says that work was *closed*, the disposition is
stated explicitly as merged, completed, superseded, or not planned; closure must
not be read as proof that an unmet requirement was satisfied.

## 1. Validated code baseline

The last code/security change admitted before this documentation-only closure
was PR #20, `security: pin CI/CD dependencies to immutable refs`.

| Field | Evidence |
| ----- | -------- |
| Validated PR #20 head | `1647dabe227c948907749b5325bbdf410eef91b5` |
| Validated synthetic merge commit | `2ee512ee4d05bad7eb27089e5145b6c32d66fb4b` |
| Validated merge base | `58967a8d244f42484ae5b60185986899441b3527` |
| Validated merge Git tree | `a90ca4d8e3091d0625d2e882468ca137a40e6182` |
| Actual PR #20 merge commit on `main` | `f92f0ca6f81beafcc08ae4eac62cc8e157863a59` |
| Actual PR #20 merge Git tree | `a90ca4d8e3091d0625d2e882468ca137a40e6182` |

The actual PR #20 merge and the fully tested synthetic merge candidate point to
the same Git tree. That establishes byte identity of the repository content for
that code baseline. The detailed workflow/test measurements are preserved in
`release-readiness-0.2.md` and PR #20.

This closure record and the associated release-readiness refresh are
**documentation-only**. Their later merge necessarily changes the repository Git
tree, but it does not change runtime, package, workflow, scientific, benchmark,
or test code. The PR #20 exact-tree evidence therefore remains evidence for the
code baseline above; it must not be misreported as an exact-tree test of later
documentation-only commits.

## 2. Pull-request disposition

PR #20 was merged after exact-candidate validation.

The dependency-update PRs #21–#29 and #31–#34 were deliberately **closed
unmerged** during final repository closure. They proposed newer workflow Action
revisions, including major runtime/tooling transitions affecting combinations of
security analysis, Python setup, artifact handling, Pages, container build and
login, provenance attestation, signing, and release-only paths.

They were not merged because accepting them at the end of a frozen release
hardening pass would invalidate the existing exact-candidate evidence and would
require a new validation cycle, including non-publishing tests of privileged
release paths that ordinary pull-request CI does not exercise. Their closure is
not evidence that the proposed versions were tested or adopted.

The migration inventory and acceptance requirements were preserved in issue
#30 before that issue was closed as **not planned for this frozen baseline**.

At repository closure, there should be no open pull request. That condition is
to be verified live after this documentation PR is merged and before branch
cleanup is declared complete.

## 3. Issue disposition

- Issue #19, immutable workflow references and supply-chain hardening, was
  completed by PR #20 and closed as completed.
- Issue #30, migration of pinned workflow Actions to newer major releases, was
  closed as **not planned** for this frozen baseline after all corresponding
  updater PRs were closed unmerged. The maintenance requirements remain in the
  historical issue record.
- Issue #17, server-side protection of `main`, was closed as **not planned** for
  this repository closure because the available repository integration does not
  expose the required branch-protection/ruleset write. This is an administrative
  disposition only: live server-side protection remains absent and the issue
  closure must never be cited as evidence that the control exists.

At repository closure, there should be no open issue. That condition is to be
verified live before the closure pass is declared complete.

## 4. Branch reconciliation

Before deletion, every substantive historical work branch was compared against
`main` using Git commit ancestry. The following branches had `ahead_by = 0` and
were therefore fully contained in `main`:

- `assurance/eac-r15-protocol`
- `assurance/p0-benchmark-claims`
- `assurance/p0-stochastic-equivalence`
- `assurance/reproducibility-py311-py312`
- `fix/ci-after-beta-merge`
- `fix/ci-mypy-opa-fmt`
- `fix/ci-opa-reproduce`
- `fix/main-ci-opa-fmt-mypy`
- `fix/opa-eval-stdin-input`
- `fix/opa-fmt-list-fail`
- `release/alpha-audit-hardening`
- `release/openapi-example-contract`
- `release/pin-github-actions`
- `remediation/0.2-assurance-semantics`
- `validation/eac-r15-protocol`

`tmp-format-probe` was a disposable formatter-repair branch. Its relevant
formatter changes were reconstructed on the clean PR #20 lineage before merge;
its temporary commits are not authoritative work to preserve.

`tmp-evidence-refresh` contains only the final documentation refresh in its net
diff from the PR #20 baseline. Its temporary workflow scaffolding deleted itself
before this closure record was added. The documentation is to be integrated via
a final documentation PR, preferably squash-merged so temporary scaffolding
history does not enter `main`.

Dependency-update branches correspond to closed unmerged updater PRs and are not
part of the frozen baseline.

After the documentation closure PR is merged, every non-`main` branch is to be
deleted. Final closure requires a live branch enumeration showing exactly one
remaining branch: `main`.

## 5. Supply-chain maintenance boundary

`.github/dependabot.yml` remains configured to check the `github-actions`
ecosystem weekly. This is intentional maintenance infrastructure. Consequently,
"only `main` remains" is a verified repository-closure snapshot, not a permanent
promise that maintenance automation can never create a future review branch.
Any future dependency update must remain reviewable and must preserve immutable
workflow pins.

## 6. Known facts that closure does not erase

Repository administration is being closed; the following facts are not being
rewritten into stronger claims:

- the package version remains `0.2.0.dev0` with a Pre-Alpha classifier;
- server-side protection/ruleset enforcement for `main` remains absent as last
  verified;
- package-index ownership/trusted-publisher configuration has not been
  established by repository evidence in this audit;
- publication Environment/approval configuration has not been established by
  repository evidence in this audit;
- independent maintainer reproduction remains an external release gate unless
  separately performed and recorded;
- an annotated, signed public-release tag and exact-tag publication evidence do
  not follow from this repository cleanup;
- automated exact-tree evidence is not equivalent to independent human review.

Therefore repository closure and branch/PR hygiene must not, by themselves, be
represented as authorization for a final public release.

## 7. Closure acceptance checklist

The repository-closure pass is complete only when all of the following are
verified after the documentation merge:

1. the final documentation PR is merged into `main`;
2. there are zero open pull requests;
3. there are zero open issues;
4. every non-`main` branch has been deleted;
5. live branch enumeration returns exactly `main`;
6. `main` contains this closure record and the refreshed release-readiness
   record;
7. no temporary cleanup workflow exists on `main`;
8. the final report preserves, rather than hides, the unresolved server-side
   protection and external-release boundaries above.
