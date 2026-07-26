# OPA obligations

Status: **available** (Milestone C2). Backend-neutral obligations compile to a
Rego v1 OPA bundle; evidence feeds the assurance case.

## Install

```bash
pip install envassure[opa]   # documents the system OPA dependency
# Install a pinned OPA binary on PATH for test/evaluate (not vendored).
# integrations.yml currently installs OPA 1.18.2 on the opa matrix job.
```

## CLI

```bash
eac obligations generate world.json -o /tmp/opa-bundle --allow-unsupported
eac obligations test /tmp/opa-bundle
eac obligations evaluate /tmp/opa-bundle -i input.json
eac obligations report world.json --json
```

Bundle members: `.manifest`, `policy.rego`, `data.json`, `schema.json`,
`policy_test.rego`, `obligation-map.json`.

Six families: authorization_preservation, resource_conservation,
deterministic_reset_replay, observation_separation, reward_trace_binding,
idempotency_safety. Unsupported obligations fail before generation unless
`--allow-unsupported`.

## Example

[`examples/opa_authorization/`](https://github.com/fraware/environment-assurance-compiler/tree/main/examples/opa_authorization)

## What is not claimed

- Base install does not require OPA.
- Generated Rego is not production policy equivalence without evaluation evidence.

## Related

- [Add authorization](../guides/add-authorization.md)
- [Validation and fidelity](../concepts/validation-and-fidelity.md)
