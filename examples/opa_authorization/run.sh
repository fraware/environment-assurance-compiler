#!/usr/bin/env bash
# Run E4 opa_authorization using installed-wheel `eac`.
# System OPA binary is optional for generate/report; required for test/evaluate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ROOT}/.example-out"
BUNDLE="${OUT_DIR}/opa-bundle"
mkdir -p "${OUT_DIR}"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi
# shellcheck source=../_python.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/_python.sh"

echo "==> eac --version"
eac --version

echo "==> refresh input/world.json from world.py"
"$PYTHON_BIN" world.py

echo "==> eac obligations report"
eac obligations report input/world.json --json | tee "${OUT_DIR}/report.json"

echo "==> eac obligations generate"
eac obligations generate input/world.json -o "${BUNDLE}" --allow-unsupported --json \
  | tee "${OUT_DIR}/generate.json"

if command -v opa >/dev/null 2>&1; then
  echo "==> opa fmt --check + opa test"
  opa fmt --check "${BUNDLE}/policy.rego" "${BUNDLE}/policy_test.rego"
  opa test --fail-on-empty "${BUNDLE}"
  echo "==> eac obligations evaluate"
  eac obligations evaluate "${BUNDLE}" -i input/eval-allow.json --json \
    | tee "${OUT_DIR}/evaluate.json"
else
  echo "notice: opa binary not on PATH; skipping fmt/test/evaluate"
fi

echo "run.sh completed; artifacts under ${OUT_DIR}"
