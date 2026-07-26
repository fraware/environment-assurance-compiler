# Release readiness — EnvAssure 0.2 RC

Milestone **EAC-R00** baseline freeze for the EnvAssure 0.2 remediation track.
This document records what HEAD claimed at freeze time, what 0.2 RC may assert,
and how to capture local quality baselines. It does **not** assert that those
baselines were green unless an entry below explicitly records measured results.

## Base revision

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
- That optional extras (`gym`, `pettingzoo`, `postgres`, `model-assisted`) are
  required for core assurance workflows.

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

## Baseline quality gates (how to capture)

Do **not** treat the following as “passed” unless you paste measured output and
date below. Commands are recorded so maintainers can freeze a known-good baseline
at the base SHA (or a later remediation SHA).

### Pytest

```bash
python -m pip install -e ".[dev]"
pytest
# Coverage gates (CI-enforced; floors from measured suite ~78% overall /
# ~83% cores / ~85% assurance / ~91% semantic):
pytest --cov=envassure --cov-report=term-missing --cov-report=xml --cov-fail-under=75
coverage report --rcfile=.coveragerc.cores       # fail-under 80
coverage report --rcfile=.coveragerc.assurance  # fail-under 80
coverage report --rcfile=.coveragerc.semantic   # fail-under 90
# Security-critical branches: prefer dedicated fail-closed unit tests over
# forcing 100% branch coverage.
```

| Capture field | Value |
| ------------- | ----- |
| Date / SHA | 2026-07-25 (working tree; post semantic-core raise) |
| Result | **195 passed**; overall ~**78%**, cores ~**83%**, assurance ~**85%**, semantic ~**91%** (branch) |
| Notes (skips / flakes) | No `pytest.mark.skip` / `xfail` markers found in `tests/`; treat unexpected skips as regression |

### Mypy

```bash
mypy
# equivalent to configured files under [tool.mypy] (src/envassure, strict)
```

| Capture field | Value |
| ------------- | ----- |
| Date / SHA | _not recorded in this freeze — run locally and paste_ |
| Result | _pending measurement_ |

### Example smoke (optional)

```bash
eac build-ir --module examples/counter/world.py -o /tmp/counter-ir.json
eac lint /tmp/counter-ir.json
eac run /tmp/counter-ir.json -a increment,increment
```

Record exit codes and any diagnostics if claiming example readiness.

## PR merge discipline

Until GitHub branch protection is fully configured for this repository:

1. **Default-branch merges require review** — no direct push of feature work to
   `main` during the R01–R17 remediation window when alternatives exist.
2. Prefer small, independently useful PRs; do not expand CLI/adapter/extra
   surface while R01–R12 are open (strategic freeze).
3. CI on `main` / PRs to `main` must stay green; prefer additive jobs that can
   succeed on pre-alpha (see `.github/workflows/ci.yml`).
4. When org access allows: enable required status checks, dismiss stale reviews,
   and restrict force-pushes on `main`.

See also
[CONTRIBUTING.md](https://github.com/fraware/environment-assurance-compiler/blob/main/CONTRIBUTING.md).

## Remediation landed (local verification)

R00–R17 implementation work landed in the working tree after the R00 freeze.
This section records **local** verification only; it does **not** claim GitHub
Actions CI was green.

| Field | Value |
| ----- | ----- |
| Date | 2026-07-25 |
| Base freeze SHA | `c52e22a3e653a1f89786a0580fb492c1e89e2eac` |
| Integration focus | Observation-separation obligations assert `compile_observation` / empty-on-deny / no full-state leak; concealed leakage probes treat missing/unknown projection as empty; CEGR four-state intake does not collapse indeterminate to match |

### Measured pytest (local)

```bash
pytest tests/ -q
# 195 passed
```

| Capture field | Value |
| ------------- | ----- |
| Date | 2026-07-25 |
| Result | **195 passed** (`pytest tests/ -q`); semantic gate **~91%** via `.coveragerc.semantic` |
| Coverage floors | overall **75** / cores **80** / assurance **80** / semantic **90** |
| GitHub CI | Not measured in this note (no push from this pass) |

### Remaining gaps vs acceptance gates

- Semantic cores meet the ≥90% fail-under; further gains still available on
  `reconciliation.cegr` (~85%) and `runtime.engine` (~82%) without using
  `# pragma: no cover` on reachable arms.
- Empirical: PR CI caps concealed at `--max-probes 20`; full ≥100
  curated+generated probes remain a local / `nightly-empirical.yml` run.
- Supply-chain / CI gates wired for 0.2: coverage fail-under (75 / 80 / 80 / 90),
  blocking `pip-audit`, extras + benchmark jobs, Gitleaks, CycloneDX SBOM
  preview, and Release workflow with GitHub build-provenance attestations.
  See [supply chain](../security/supply-chain.md). Local attestation verify
  against a published tag is still an operator step at release time.
- Mypy / example smoke not re-recorded in this pass.

### Public beta (`0.2.0b1`) integration honesty

| Integration | In-tree status | CI caveat |
| ----------- | -------------- | --------- |
| Gymnasium | Release-qualified adapter + E5 example | `integrations.yml` gym job |
| OpenEnv | Adapter + export/test/serve-smoke; pin `0.4.1` | No full HTTP claim; OpenEnv image optional on release |
| OPA | Bundle generate/report always | `opa fmt`/`test` need system binary (CI pin `1.18.2`) |
| Differential | In-process HTTP refund + planted mismatch | Compose only when `ENVASURE_RUN_COMPOSE=1` + Docker |

Manual DoD still open: PyPI/TestPyPI name claim, GitHub Environments, independent
maintainer repro of an RC, annotated signed `v0.2.0b1` tag cut.

## Related docs

- [Compatibility / deprecation](../compatibility.md)
- [Fidelity claims guide](../guides/fidelity-claims.md)
- [Report an environment defect](../guides/report-environment-defect.md)
- [Ten-minute tutorial](../guides/ten-minute-tutorial.md)
- [Supply chain (SBOM / attestations)](../security/supply-chain.md)
