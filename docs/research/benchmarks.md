# Benchmarks

EnvAssure currently ships an offline semantic-regression harness plus the
protocol for a separate qualification-grade hidden-reference experiment.
These are deliberately different evidence classes.

## 1. Shipped semantic-regression suite

Small fixtures:

```bash
eac benchmark benchmarks/fixtures/counter_oracle.json --json
eac benchmark benchmarks/fixtures/auth_oracle.json --json
eac benchmark benchmarks/fixtures/inventory_oracle.json --json
eac benchmark --suite --json
```

Larger generated suite:

```bash
# `--concealed` is a historical CLI name retained for compatibility.
eac benchmark --concealed --json
eac benchmark benchmarks/fixtures/transactional_enterprise.json --json
eac benchmark benchmarks/fixtures/authorization_heavy.json --json
eac benchmark benchmarks/fixtures/stochastic_operational.json --json
```

The uncapped run contains at least 100 curated and 100 generated probes per
workflow. PR CI may cap it with `--max-probes 20`; the scheduled
`.github/workflows/nightly-empirical.yml` job runs it uncapped.

### Claim boundary

This suite is **not EAC-R15 scientific qualification**. The generator and oracle
construction code are public in this repository, and
`envassure.benchmark.workflows.build_workflow_oracle` materializes both sides of
the fixture comparison. The suite therefore establishes only things such as:

- regression stability of the comparison machinery;
- preservation/detection of planted negative controls;
- deterministic fixture and digest behavior;
- dimension-separated metric plumbing.

It does **not** establish that EnvAssure can reconstruct an operational system
from incomplete/conflicting source material, abstain correctly when semantics
are underdetermined, or generalize to independently concealed held-out
behavior. Repository documentation and release notes must not describe the
shipped suite as evidence for those stronger propositions.

The historical `hidden_oracle_digest` field is a fixture-integrity digest; it is
not proof that the oracle implementation was hidden from the compiler or its
developers.

### Generated workflow coverage

| Workflow | Regression focus |
| --- | --- |
| `transactional_enterprise` | Ledger / refund / idempotency / retry |
| `authorization_heavy` | Multi-role deny paths and observation separation |
| `stochastic_operational` | Categorical stockout branches; underpowered samples |

Metrics remain dimension-separated (`transition_agreement`, `auth_agreement`,
`failure_agreement`, `observation_agreement`, `leakage`, `solvability`,
`diff_match`). Do not collapse them into a scalar fidelity score.

Intentional negative controls remain mandatory, including fail-open
authorization, evaluator-only observation leakage, and underpowered stochastic
comparisons. Suppressing a negative control is a methodology failure.

## 2. Qualification-grade hidden-reference protocol (EAC-R15)

A result may be labelled `scientifically_qualified` only after the following
experiment is run against independently maintained reference systems or sealed
reference services. Merely adding more generated fixtures does not satisfy this
protocol.

### Experimental unit

Each unit starts from a source package available to the EnvAssure construction
process, not from an oracle trajectory. The package should contain a controlled
mixture of operational documentation, schemas/contracts, policies, traces and
procedures. It must intentionally include incomplete and conflicting evidence
where realistic.

EnvAssure must execute the normal path:

`source adapters -> candidate facts -> provenance/conflict analysis -> explicit
reconciliation/abstention -> authoritative IR -> validation/obligations ->
executable environment -> held-out differential probes`.

The reference implementation, hidden labels and held-out probes must be outside
the compiler/worker trust domain until evaluation.

### Required workflow families

At minimum, qualify three materially different reference workflows:

1. transactional enterprise behavior: atomicity, retries, idempotency, failures;
2. authorization-heavy behavior: roles, delegation, scope, tenant boundaries,
   deny paths and observation separation;
3. stochastic operational behavior: distributions, rare branches, stateful
   dynamics and declared equivalence margins.

### Minimum probe plan

For each reference workflow, use at least 100 adjudicated held-out probes after
construction. Probe generation and reference outputs must be sealed before the
candidate environment is evaluated. Public development probes must be distinct
from qualification probes.

### Primary estimands

Report, separately:

- fact recovery precision/recall by evidence class;
- wrong semantic commitment rate;
- correct abstention rate on genuinely underdetermined facts;
- incorrect abstention rate where evidence is sufficient;
- unresolved/conflicting fact rate and adjudication disposition;
- transition, authorization, failure, observation and idempotency agreement;
- stochastic equivalence intervals for preregistered distributional quantities;
- leakage violations;
- counterexamples found and CEGR iterations to convergence;
- expert correction time and number of expert decisions per workflow;
- performance on held-out behavior not directly demonstrated in source traces.

Never replace these with an overall fidelity average.

### Negative results and missing evidence

A required dimension that is underpowered, unavailable, or semantically
inapplicable must be reported as `indeterminate` or `not_applicable` under the
existing four-state model. It cannot be converted to `match` to obtain an
overall pass. Wrong commitments and negative results remain in the public
experiment artifact.

### Qualification evidence bundle

A qualification bundle must bind at least:

- reference-system/custodian identifier and immutable digest where possible;
- source-package digest;
- EnvAssure commit/release digest and environment IR digest;
- declared semantic assumptions and applicability regime;
- reconciliation/abstention decisions;
- held-out probe manifest commitment before evaluation;
- raw dimension results plus the preregistered statistical plan;
- counterexamples/refinements;
- independent reviewer sign-off or an explicit `internally_verified` status if
  independent review has not occurred.

## Independent reproduction

Reproducing the shipped semantic-regression suite is useful software evidence,
but it must be named as such. A clean-room reproduction of EAC-R15 additionally
requires an independent party/custodian to preserve the oracle and held-out
probe boundary. That external step cannot be self-certified by this repository.

## What current results mean

Current benchmark exit success means the fixture checks passed for their
declared expectations. It is **not** evidence of production parity, independently
concealed reconstruction accuracy, or deployment validity.

## Related

- [Methodology](methodology.md)
- [Limitations](limitations.md)
- [Differentially validate](../guides/differentially-validate.md)
