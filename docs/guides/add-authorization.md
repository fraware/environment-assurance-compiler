# Add authorization

This guide walks through the multi-actor authorization reference pack at
`examples/auth/`.

## Prerequisites

```bash
pip install -e ".[dev]"
```

## 1. Build and lint the auth world

```bash
eac build-ir --module examples/auth/world.py -o examples/auth/ir/world.json
eac lint examples/auth/ir/world.json
```

The world defines:

- Actors `requester` and `approver` with distinct available actions.
- Action `approve` / `deny` requiring `authorization: role:approver`.
- Approver `authority_source: role:approver` so static analysis can discharge
  the authority check (`EAC4004` must not fire on the clean pack).
- Hidden oracle state `approver_id` (`evaluator_visible=true`,
  `policy_visible=false`) omitted from `requester_view`.

## 2. Analyze authority and information flow

```bash
eac analyze examples/auth/ir/world.json --json
```

Pass criteria for the clean pack:

- No `EAC4004` (authority/delegation) on `approve` / `deny`.
- No `EAC5002` (evaluator state leaked into a policy observation).

Inject a defect and confirm detection (Python):

```bash
python - <<'PY'
import importlib.util
from pathlib import Path
from envassure.analysis import analyze_world, apply_mutation
from envassure.analysis.mutation import MutationCategory

root = Path("examples/auth/world.py")
spec = importlib.util.spec_from_file_location("auth_world", root)
mod = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(mod)
world = mod.build_auth_world()
mutant = apply_mutation(world, MutationCategory.AUTHORITY, seed=0)
codes = {d.code for d in analyze_world(mutant).report.diagnostics}
assert "EAC4004" in codes, codes
print("authority defect detected", sorted(codes & {"EAC4004"}))
PY
```

## 3. Run a permitted sequence

```bash
eac run examples/auth/ir/world.json -a submit,approve --json
```

Use actor-aware sequences in richer runtimes; the CLI smoke path executes the
declared action graph. For permission probes, plan differential auth probes:

```bash
eac differential examples/auth/ir/world.json --max-probes 32 --json
```

Probe kinds include `auth.*.denied` when actions declare authorization.

## 4. Package with version metadata

```bash
eac package examples/auth/ir/world.json -o auth.eap
eac verify-pack auth.eap
```

`verify-pack` fails closed on checksum or secret-scan issues (`EAC8006`).

## Checklist

| Check | Expected |
| --- | --- |
| `eac lint` | Reference integrity OK |
| `eac analyze` | No `EAC4004` / `EAC5002` on clean IR |
| Mutation `AUTHORITY` | Yields `EAC4004` |
| Mutation `OBSERVATION_LEAK` | Yields `EAC5002` |
| Pack | `verify-pack` OK |
