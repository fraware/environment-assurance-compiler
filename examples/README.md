# Reference projects

Public examples follow the contract under each directory that ships an
`example-manifest.json`:

```text
README.md, pyproject.toml (or lock), input/, expected/, run.sh, verify.sh,
example-manifest.json
```

Lint manifests:

```bash
python scripts/lint_example_manifests.py
```

| ID | Example | Status | Focus |
| -- | ------- | ------ | ----- |
| E1 | [`refund/`](refund/) | contract-complete | OpenAPI + SOP + trace conflict → decide → IR |
| E2 | [`openenv_refund/`](openenv_refund/) | contract-complete | OpenEnv export/test/serve-smoke (`openenv==0.4.1`) |
| E3 | [`reference_systems/refund_service/`](reference_systems/refund_service/) | contract-complete | HTTP refund + planted mismatch; Compose optional |
| E4 | [`opa_authorization/`](opa_authorization/) | contract-complete | OPA Rego v1 obligations (system `opa` optional) |
| E5 | [`gymnasium_edge/`](gymnasium_edge/) | contract-complete | Gymnasium Dict actions + `check_env` |

Additional in-tree references (not yet on the E1–E5 contract):

| Example | Focus | Description |
| ------- | ----- | ----------- |
| [`counter/`](counter/) | Deterministic runtime | Manual SDK counter; pack + differential fixtures |
| [`auth/`](auth/) | Authorization / observability | Multi-actor approve/deny with hidden oracle |
| [`inventory/`](inventory/) | Stochastic transitions | Categorical fulfill/stockout branches |

## Counter quick path

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
eac run examples/counter/ir/world.json -a increment,increment
eac package examples/counter/ir/world.json -o counter.eap
eac verify-pack counter.eap
```

## Refund (E1) wheel path

```bash
pip install dist/envassure-*.whl   # from a clean build
./examples/refund/run.sh
./examples/refund/verify.sh
```

Guides that use these projects live under [`docs/guides/`](../docs/guides/).
