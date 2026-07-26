#!/usr/bin/env bash
# Verify E4 opa_authorization bundle contract.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPECTED="${ROOT}/expected/bundle-members.json"
OUT_DIR="${ROOT}/.example-out"
BUNDLE="${OUT_DIR}/opa-bundle"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi
# shellcheck source=../_python.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_python.sh"

if [[ ! -f "${EXPECTED}" ]]; then
  echo "error: missing ${EXPECTED}" >&2
  exit 1
fi

if [[ ! -f input/world.json ]]; then
  "$PYTHON_BIN" world.py
fi

mkdir -p "${OUT_DIR}"
eac obligations generate input/world.json -o "${BUNDLE}" --allow-unsupported >/dev/null

"$PYTHON_BIN" - <<PY
import json
from pathlib import Path

root = Path(".").resolve()
bundle = Path(r"${BUNDLE}")
# Prefer relative bundle under cwd when Git Bash path is opaque to Windows Python.
if not bundle.exists():
    bundle = root / ".example-out" / "opa-bundle"
expected = json.loads((root / "expected" / "bundle-members.json").read_text(encoding="utf-8"))
for name in expected["members"]:
    path = bundle / name
    assert path.is_file(), f"missing {name}"
policy = (bundle / "policy.rego").read_text(encoding="utf-8")
assert "import rego.v1" in policy
for family in expected["required_families"]:
    assert family in policy, family
print("ok", len(expected["members"]), "members")
PY

if command -v opa >/dev/null 2>&1; then
  opa fmt --check "${BUNDLE}/policy.rego" "${BUNDLE}/policy_test.rego"
  opa test --fail-on-empty "${BUNDLE}"
else
  echo "notice: opa binary not on PATH; bundle member checks only"
fi

echo "verify.sh passed"
