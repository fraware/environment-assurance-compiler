# Release readiness — EnvAssure 0.2 RC

Milestone **EAC-R00** baseline freeze for the EnvAssure 0.2 remediation track.
This document preserves the historical freeze evidence and records newer release
candidate evidence in explicitly dated sections. A green structural or CI gate
must never be interpreted as proof of production behavioral parity or high
fidelity unless the corresponding fidelity claim has its own evidence.

## Latest exact-tree evidence — post PR #20 (2026-08-26)

This is the newest repository-level evidence snapshot and supersedes earlier
"current" snapshots below. Historical snapshots remain preserved for auditability.
A green structural, CI, package, or integration gate is evidence only for the
proposition it actually exercises; it is not production behavioral-parity or
high-fidelity evidence by itself.

| Field | Evidence |
| ----- | -------- |
| Current `main` merge commit | `f92f0ca6f81beafcc08ae4eac62cc8e157863a59` |
| Current `main` Git tree | `a90ca4d8e3091d0625d2e882468ca137a40e6182` |
| Validated PR #20 head | `1647dabe227c948907749b5325bbdf410eef91b5` |
| Validated PR #20 synthetic merge commit | `2ee512ee4d05bad7eb27089e5145b6c32d66fb4b` |
| Validated merge base | `58967a8d244f42484ae5b60185986899441b3527` |
| Validated merge Git tree | `a90ca4d8e3091d0625d2e882468ca137a40e6182` |
| Package version | `0.2.0.dev0` — **Pre-Alpha**, not Beta |
| Python matrix | 3.11 / 3.12 / 3.13 |

The tested PR synthetic merge commit and the actual merged `main` commit point
to the **same Git tree**. The repository content on `main` is therefore
byte-identical to the merge tree exercised by the PR gates.

### Exact merge-tree CI evidence for PR #20

All seven required workflow groups were terminal green on the exact PR #20
synthetic merge candidate before merge:

- **CI** — success.
- **Docs** — success (`mkdocs build --strict`).
- **Security** — success: checksum-verified Gitleaks acquisition and repository
  history scan, blocking dependency audit, CodeQL, and Trivy.
- **Integrations** — success across Gym, OpenEnv, OPA, and differential; the OPA
  job exercised the separately checksum-verified pinned OPA binary path.
- **Test Release** — success: distributions built, wheel installed in a fresh
  environment, acceptance/smoke passed, and dry-run checksums/release manifest
  were produced.
- **Cross-Python reproducibility** — success: Python 3.11 and 3.12 canonical
  evidence independently built and verified; required byte and semantic identity
  passed.
- **Reproduce** — success: benchmark packs linted/verified, the reproducibility
  bundle regenerated and verified in-tree, then downloaded and verified in a
  second job without a source checkout.

Python 3.12 CI recorded:

| Gate | Measured result | Enforced floor |
| ---- | --------------- | -------------- |
| Test collection | **348 collected; 333 passed; 15 expected skips** | no unexpected failure |
| Overall branch coverage | **75.68%** | ≥75% |
| Core coverage | **84%** | ≥80% |
| Assurance coverage | **85%** | ≥80% |
| Semantic-core coverage | **91%** | ≥90% |
| Ruff lint | passed across `src`, `tests`, and `scripts` | blocking |
| Ruff format | **179 files already formatted** | blocking |
| Mypy | **no issues in 131 source files** | blocking |
| Workflow Action immutability | checker passed across all workflows | blocking |

The 15 base-matrix skips remain attributable to intentionally absent optional
integration dependencies/binaries or Docker Compose. Dedicated extras and
integration jobs separately exercised the release-qualified Gym, PettingZoo,
OPA, OpenEnv, and differential paths. These skips are not represented as tested
coverage of absent dependencies.

### Supply-chain hardening state

Issue #19 / PR #20 closed the mutable-workflow-reference defect. Remote workflow
Actions are pinned to exact commits; CI rejects future mutable remote `uses:`
references; container actions, if introduced, must use SHA-256 digests; weekly
GitHub-Actions dependency updates arrive as explicit reviewable changes; and the
Gitleaks archive is checksum-verified before extraction. These controls improve
reproducibility and tamper resistance but do not independently establish trust
in upstream source code.

The final CI logs also contain runner warnings that some currently pinned Action
revisions target a deprecated Node runtime and are being executed by the runner
under Node 24. This did not fail the tested candidate, but it is maintenance debt
to address through reviewed Action updates rather than by returning to movable
tags.

### Current release decision boundary

This snapshot is a strong **pre-alpha development baseline**. It is **not**
authorization to cut `v0.2.0b1`, an RC, or a final public release.

Known gates still open include:

- issue #17: live server-side protection/ruleset enforcement for `main` is still
  absent; repository CI configuration is not equivalent to enforced branch
  policy;
- PyPI/TestPyPI package-name ownership and trusted-publisher setup have not been
  independently verified from this repository audit;
- required publication Environments and approval policies have not been
  independently verified;
- independent maintainer reproduction of the release candidate remains an
  external release gate;
- an annotated, signed release tag and exact-tag Release-workflow evidence do
  not yet exist for the intended public release;
- the package remains `0.2.0.dev0` with the Pre-Alpha classifier;
- PR #20 had no submitted human review object; automated exact-tree evidence is
  not represented as satisfying a future human-governance requirement.

The merge performed through the repository integration produced `main` commit
`f92f0ca6f81beafcc08ae4eac62cc8e157863a59`. The admissible post-merge evidence
is exact Git-tree identity with the fully tested synthetic merge tree above.
Do not infer a fresh merged-`main` workflow run unless one is separately
observed and recorded.


## Historical exact-tree evidence — PR #16 (2026-08-26)

This is the newest repository-level evidence snapshot. It supersedes the July
quality measurements for the current development baseline, but does **not** erase
or rewrite the historical R00 freeze recorded below.

| Field | Evidence |
| ----- | -------- |
| Current `main` commit after PR #16 | `e2718eefca0e17d989ae3bee6df4d03299c0fe61` |
| Current `main` Git tree | `57e8f250f1ba9ca2455c30072ec18c7995ce2228` |
| Validated PR #16 merge commit | `098131303bb79f9383714ba0dabcd0ac7187d297` |
| Validated PR #16 head | `76f115701a2f37f2e2fb185ea3fbd03b0a3572de` |
| Validated merge base | `0ffaa860ab25a98f24cd746054e140c10ea844d7` |
| Validated merge Git tree | `57e8f250f1ba9ca2455c30072ec18c7995ce2228` |
| Package version | `0.2.0.dev0` — **Pre-Alpha**, not Beta |
| Python matrix | 3.11 / 3.12 / 3.13 |

The tested PR merge commit and the actual merged `main` commit point to the
**same Git tree**. The repository content on `main` is therefore byte-identical
to the merge tree exercised by the PR gates. The commit objects differ because
the final merge has a different commit message/timestamp, not because the tree
content differs.

### Exact merge-tree CI evidence

All six release-critical PR workflows were terminal green on the exact PR #16
candidate before merge:

- **CI** — success.
- **Docs** — success (`mkdocs build --strict`).
- **Security** — success, including blocking Gitleaks, dependency audit, CodeQL,
  and Trivy gates.
- **Integrations** — success after rerunning one externally failed OPA-download
  job; Gym, OpenEnv, differential, and OPA integration jobs all completed.
- **Test Release** — success from a freshly built/installed wheel, including the
  public E1 example contract.
- **Cross-Python reproducibility** — success.

Python 3.12 CI recorded:

| Gate | Measured result | Enforced floor |
| ---- | --------------- | -------------- |
| Test collection | **342 collected; 327 passed; 15 expected skips** | no unexpected failure |
| Overall branch coverage | **75.68%** | ≥75% |
| Core coverage | **84%** | ≥80% |
| Assurance coverage | **85%** | ≥80% |
| Semantic-core coverage | **91%** | ≥90% |
| Ruff | passed | blocking |
| Ruff format | **168 files already formatted** | blocking |
| Mypy | **no issues in 131 source files** | blocking |

The 15 base-matrix skips are attributable to intentionally absent optional
integration dependencies/binaries or Docker Compose. Those paths are not treated
as silently covered: dedicated extras and integration jobs separately exercise
the release-qualified Gym/PettingZoo/OPA/OpenEnv paths, while Compose remains an
explicit conditional integration.

The OPA rerun is substantive evidence rather than a wrapper-only green result:
OPA `1.18.2` installed, **6 OPA integration tests passed**, the generated bundle
contained **7 obligations**, `opa test --fail-on-empty` passed **2/2**, the public
OPA example evaluated successfully, and its `verify.sh` passed. The first OPA
attempt failed before tests because the upstream binary download terminated with
`curl` code 56; that transport weakness is being hardened separately.

### E1 evidence and claim boundary

PR #16 completed issue #8's OpenAPI-backed example contract. E1 imports OpenAPI,
procedure, and trace evidence; distinguishes event observations from canonical
action semantics; carries inferred facts as inferred; preserves a genuine retry
policy disagreement as an unresolved ambiguity; fails closed where executable
semantics are unresolved; runs only the modeled non-timeout path; packages; and
verifies the pack.

E1 still **does not** establish authoritative timeout-state semantics, a resolved
retry policy, idempotency behavior, or correctness of the live payment rail. It
remains **EF-0**, with no expert decision artifact. `verify-pack` establishes
pack structure/integrity only; it is not empirical validation or production
parity evidence.

### Merged-`main` workflow caveat

The merge was performed through the connected GitHub integration. At the time of
this evidence capture, GitHub had emitted **no new push-triggered workflow set**
for commit `e2718eefca0e17d989ae3bee6df4d03299c0fe61`. Do not report a fresh
merged-`main` Actions run that did not occur. The admissible evidence here is the
identity of the final `main` Git tree with the merge tree that all six PR gates
actually exercised.

A later PR that changes this tree must obtain its own fresh merge-candidate
evidence; tree identity does not transfer across later changes.

### Current release decision boundary

This snapshot is acceptable as a **current pre-alpha development baseline**. It
is **not** authorization to cut `v0.2.0b1`, an RC, or a final release.

Known gates still open before public beta/final release include:

- issue #17: live server-side protection/ruleset enforcement for `main` remains
  absent; CI configuration in the repository is not equivalent to enforced
  branch policy;
- PyPI/TestPyPI package-name and trusted-publisher setup;
- required GitHub Environments and approvals for publication targets;
- independent maintainer reproduction of a release candidate;
- annotated, signed release tag and exact-tag release workflow evidence;
- final release-candidate documentation/evidence refresh after remaining
  hardening changes;
- supply-chain hardening of mutable GitHub Action references before final
  release, unless an explicitly documented risk decision is made.

PR #16 was merged without a submitted GitHub review object after exact-tree CI
and adversarial technical audit. That should **not** be treated as satisfying a
future beta/final human-governance requirement. Formal branch/ruleset enforcement
remains issue #17's acceptance boundary.

## Base revision — historical R00 freeze

| Field | Value |
| ----- | ----- |
| Recorded at | 2026-07-25 |
| Command | `git rev-parse HEAD` |
| Base SHA | `c52e22a3e653a1f89786a0580fb492c1e89e2eac` |
| Package version at freeze | `0.1.0a0` (pre-alpha) |
| Target identity | package `envassure`, CLI `eac`, versioned toward **0.2.0rc** |

Short form cited in the remediation plan audit: `c52e22a…`.

## Claim inventory

Aligned with [limitations](limitations.md) and
[validation and fidelity](../concepts/validation-and-fidelity.md).

### 0.2 RC **may** claim

- Local-first compilation of operational evidence into typed Environment IR
  (`WorldDefinition`), with explicit migrate (`eac migrate`) only.
- Fail-closed CLI/SDK behavior for unsupported inputs (non-zero exit / stable
  diagnostics; never silent success for unimplemented work).
- Event-sourced reference runtime with reset / step / snapshot / restore / fork
  for IR that the current runtime profile supports.
- Multi-dimensional fidelity **profiles** and assurance artifacts (diagnostics,
  differential reports, packs, HTML/JSON cases) that cite evidence.
- Offline differential plumbing against fixtures / simulators when configured
  correctly.
- Plugin and proposal-provider extension points under a versioned plugin API,
  treated as untrusted until allowlisted / verified.

### 0.2 RC **must not** claim

- Production behavioral parity or “full vision” fidelity from a successful
  `build-ir` / `lint` / `package` alone.
- That OpenAPI / DDL / SOP / trace import yields a finished high-fidelity world
  (imports yield **facts**, not authoritative IR without reconciliation/decisions).
- Automatic trust for third-party packs or plugins.
- Silent repair of missing operational semantics.
- An RL trainer, model-serving platform, general-purpose proof assistant, or
  single-number composite fidelity leaderboard.
- That optional extras (`gym`, `pettingzoo`, `postgres`, `model-assisted`, `opa`,
  `openenv`) are required for core assurance workflows.

Strategic freeze during remediation (R01–R12): **no new CLI commands, adapters,
or extras** until those milestones land. See the remediation plan.

**Status (2026-07-26):** the R00 adapter/CLI freeze is **lifted** for the public
`0.2` beta track. New surfaces (obligations, connector, OpenEnv, pack CLI) are
in tree on `0.2.0.dev*`; cutting `v0.2.0b1` remains gated on the beta DoD
(PyPI name claim, Environments, independent maintainer repro).

## Public CLI inventory

Source of truth:
[`src/envassure/cli/app.py`](https://github.com/fraware/environment-assurance-compiler/blob/main/src/envassure/cli/app.py).
Entry point: `eac` (`envassure.cli.main:app`). Global: `-h`/`--help`, `-V`/`--version`.

| Command | Registration phase (comment in app) | Role |
| ------- | ----------------------------------- | ---- |
| `init` | Phase 0 | Create workspace |
| `doctor` | Phase 0 | Environment / lock checks |
| `inspect` | Phase 0 | Summarize workspace or IR |
| `build-ir` | Phase 1 | Compile manual SDK module → IR |
| `lint` | Phase 1 | Reference / integrity checks |
| `diff` | Phase 1 | Semantic IR difference classification |
| `explain` | Phase 1 | Provenance / element explanation |
| `generate` | Phase 1 | Schema / codegen export |
| `migrate` | Phase 1 | Explicit IR version upgrade |
| `import` | Phase 2 | Adapters: `openapi` \| `database` \| `policy` \| `procedure` \| `traces` |
| `facts` | Phase 2 | List facts; `--reconcile` |
| `ambiguities` | Phase 2 | List ambiguity records |
| `decide` | Phase 2 | Record expert decision |
| `run` | Phase 3 | Execute actions on reference runtime |
| `snapshot` | Phase 3 | Persist restoreable snapshot |
| `replay` | Phase 3 | Replay / digest verification |
| `test` | Phase 3 | Determinism smoke (identical sequences) |
| `analyze` | Phase 4 | Static analyses |
| `coverage` | Phase 4 | Multi-dimensional coverage |
| `differential` | Phase 5 | Offline differential probes |
| `refine` | Phase 5/6 | CEGR intake / refinement generations |
| `package` | Phase 5/6 | Build `.eap` pack |
| `verify-pack` | Phase 5/6 | Checksums + secret-scan gates |
| `report` | Phase 5/6 | Assurance-case JSON/HTML |
| `benchmark` | Phase 5/6 | Offline fixture-oracle harness |
| `plugins` | Phase 5/6 | Subcommands: `list`, `create`, `test`, `package`, `doctor` |

`STUB_COMMANDS` is empty: all registered commands have real implementations and
must fail closed on unsupported inputs.

Narrative reference: [CLI reference](../reference/cli.md).

## Public Python API inventory (package surface)

Top-level re-exports from `envassure` (`src/envassure/__init__.py`):

| Symbol | Role |
| ------ | ---- |
| `__version__` | Package version string |
| `World` | Manual authoring builder (`envassure.api`) |
| `action`, `actor`, `state`, `task` | Authoring helpers / decorators |

Broader SDK modules (importable but not all re-exported at top level) include
IR models/validation, runtime, sources, reconciliation, differential, packs,
plugins, obligations, tasks, and analysis. Treat non-`__all__` surfaces as
unstable under the [compatibility policy](../compatibility.md) until a stable
channel exists.

## Known limitations

Authoritative list: [limitations](limitations.md).

Honest fidelity bounds and operational constraints (local-first, explicit
migrate, pre-alpha API churn) apply unchanged to the 0.2 RC track.

## Baseline quality gates — historical capture instructions

The commands below are retained as part of the R00 historical record. The current
measured evidence is the dated section at the top of this document.

```bash
python -m pip install -e ".[dev]"
pytest --cov=envassure --cov-report=term-missing --cov-report=xml --cov-fail-under=75
coverage report --rcfile=.coveragerc.cores       # fail-under 80
coverage report --rcfile=.coveragerc.assurance  # fail-under 80
coverage report --rcfile=.coveragerc.semantic   # fail-under 90
mypy
```

Historical July capture:

| Capture field | Value |
| ------------- | ----- |
| Date / SHA | 2026-07-25 (working tree; post semantic-core raise) |
| Result | **195 passed**; overall ~**78%**, cores ~**83%**, assurance ~**85%**, semantic ~**91%** (branch) |
| Mypy | not recorded in the R00 freeze |
| Notes | historical local result; do not substitute it for the 2026-08-26 exact-tree evidence above |

## Explicit migration evidence

The release suite includes direct migration coverage rather than relying only on
schema compatibility claims. Current tests exercise:

- the two-minor read window (`0.1.0` and `0.2.0`);
- additive `0.1.0 → 0.2.0` transforms and deprecated `profile` normalization;
- migrated-document validation and file round-trip;
- dry-run behavior without writes;
- current-version no-op behavior;
- fail-closed rejection of unknown versions;
- CLI migration from `0.1.0` to `0.2.0`;
- proof that `verify-pack` does **not** silently migrate a pack.

This is the evidence basis for the public statement that migration is explicit.

## PR merge discipline

Until GitHub branch protection is fully configured for this repository:

1. No ordinary direct push of feature work to `main` when a PR path exists.
2. Validate the actual PR merge candidate, not only the feature-branch head.
3. Any new commit invalidates earlier exact-head green evidence.
4. For beta/final release, require formal review and server-side enforcement;
   exact-tree automated evidence alone does not substitute for that governance.
5. When org/repository access allows, enable required status checks, stale-review
   dismissal, up-to-date merge validation, and force-push/deletion restrictions.

See also
[CONTRIBUTING.md](https://github.com/fraware/environment-assurance-compiler/blob/main/CONTRIBUTING.md).

## Remediation landed — historical local verification

R00–R17 implementation work landed in the working tree after the R00 freeze.
This section records the historical **local** July verification only; it does
**not** override the current exact-tree evidence above.

| Field | Value |
| ----- | ----- |
| Date | 2026-07-25 |
| Base freeze SHA | `c52e22a3e653a1f89786a0580fb492c1e89e2eac` |
| Integration focus | Observation-separation obligations assert `compile_observation` / empty-on-deny / no full-state leak; concealed leakage probes treat missing/unknown projection as empty; CEGR four-state intake does not collapse indeterminate to match |

### Measured pytest (historical local)

```bash
pytest tests/ -q
# 195 passed
```

| Capture field | Value |
| ------------- | ----- |
| Date | 2026-07-25 |
| Result | **195 passed** (`pytest tests/ -q`); semantic gate **~91%** via `.coveragerc.semantic` |
| Coverage floors | overall **75** / cores **80** / assurance **80** / semantic **90** |
| GitHub CI | Not measured in this historical note |

### Remaining gaps vs acceptance gates

- Empirical: PR CI caps concealed at `--max-probes 20`; full ≥100
  curated+generated probes remain a local / `nightly-empirical.yml` run.
- Supply-chain / CI gates wired for 0.2 include coverage fail-under
  (75 / 80 / 80 / 90), blocking `pip-audit`, extras + benchmark jobs, Gitleaks,
  CycloneDX SBOM preview, and the Release workflow with GitHub build-provenance
  attestations. See [supply chain](../security/supply-chain.md).
- Local attestation verification against a published tag remains an operator step
  at release time.
- Mutable GitHub Action major-version references remain a supply-chain trust edge
  to eliminate or explicitly accept before final release.

### Public beta (`0.2.0b1`) integration honesty

| Integration | In-tree status | CI caveat |
| ----------- | -------------- | --------- |
| Gymnasium | Release-qualified adapter + E5 example | dedicated `Integrations` gym job |
| OpenEnv | Adapter + export/test/serve-smoke; pin `0.4.1` | No full HTTP claim; OpenEnv image optional on release |
| OPA | Bundle generation/evaluation with system OPA `1.18.2` | binary acquisition is external and is being checksum/retry hardened |
| Differential | In-process HTTP refund + planted mismatch | Compose only when `ENVASURE_RUN_COMPOSE=1` + Docker |

Manual beta DoD still open: PyPI/TestPyPI name claim, GitHub Environments,
independent maintainer reproduction of an RC, and an annotated signed
`v0.2.0b1` tag cut with exact-tag release evidence.

## Related docs

- [Compatibility / deprecation](../compatibility.md)
- [Fidelity claims guide](../guides/fidelity-claims.md)
- [Report an environment defect](../guides/report-environment-defect.md)
- [Ten-minute tutorial](../guides/ten-minute-tutorial.md)
- [Supply chain (SBOM / attestations)](../security/supply-chain.md)
