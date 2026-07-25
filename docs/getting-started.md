# Getting started

## Install

Requires Python **3.11**, **3.12**, or **3.13**.

```bash
pip install -e ".[dev]"
eac --version
```

Optional extras (`gym`, `pettingzoo`, `postgres`, `model-assisted`, `docs`) are
documented in the repository README. Missing extras fail closed with `EAC9003`.

Prefer the timed walkthrough: [Ten-minute tutorial](guides/ten-minute-tutorial.md).

## Create a workspace

```bash
eac init my-env
cd my-env
eac doctor
```

This creates `eac.toml`, `sources.yml`, directories for sources / facts / decisions /
IR / generated / validation / reports, and `.eac/` lock files. Network checks are
off unless you pass `--network`.

## Author or import a world

**Manual SDK** (recommended first path):

```python
from envassure import World, state, action

world = World("demo.counter", "Counter")
world.state("count", type="scalar")
world.action("increment")
# ... see examples/counter/world.py
```

Compile from a module that exports `build_*_world()`:

```bash
eac build-ir --module examples/counter/world.py -o examples/counter/ir/world.json
eac lint examples/counter/ir/world.json
```

**Import path:** `eac import openapi|database|policy|procedure|traces …` then
`eac facts --reconcile`, resolve open ambiguities with `eac decide`, and project
or author IR.

## Run, analyze, package

```bash
eac run examples/counter/ir/world.json -a increment,increment
eac analyze examples/counter/ir/world.json
eac package examples/counter/ir/world.json -o counter.eap
eac verify-pack counter.eap
```

Notes:

- `eac run` uses `--actions` / `-a` (comma-separated action ids or `actor:action`).
- Unsupported IR versions fail closed (`EAC3004`). Upgrade explicitly with
  `eac migrate` (never silent on verify/lint).
- Packs are untrusted until verified — see the
  [threat model](security/threat-model.md).
- Successful package/verify is not a fidelity certificate — see
  [Fidelity claims](guides/fidelity-claims.md).

## Next reading

- [Ten-minute tutorial](guides/ten-minute-tutorial.md)
- [Sources and facts](concepts/sources-and-facts.md)
- [Environment IR](concepts/environment-ir.md)
- Guides under [guides/](guides/build-from-openapi.md)
- [CLI reference](reference/cli.md)
- [Report an environment defect](guides/report-environment-defect.md)
