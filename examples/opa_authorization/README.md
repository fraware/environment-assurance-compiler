# OPA authorization example (E4)

Compile proof obligations and emit a Rego v1 OPA bundle.

## Requirements

- `pip install envassure[opa]` (documents the OPA system dependency)
- System [OPA](https://www.openpolicyagent.org/) binary on `PATH` for `test` / `evaluate`
  (CI should pin an exact OPA release; the binary is **not** vendored into the wheel)

## Commands

```bash
python examples/opa_authorization/world.py
eac obligations generate examples/opa_authorization/input/world.json -o /tmp/opa-bundle --allow-unsupported
eac obligations report examples/opa_authorization/input/world.json --json
# optional, requires opa:
eac obligations test /tmp/opa-bundle
eac obligations evaluate /tmp/opa-bundle -i examples/opa_authorization/input/eval-allow.json
```

## Status

Interface conformance for obligation generation. OPA eval evidence feeds the
assurance-case fragment; it is **not** a production-fidelity claim.
