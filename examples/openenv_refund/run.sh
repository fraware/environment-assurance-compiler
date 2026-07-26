#!/usr/bin/env bash
# Run E2 openenv_refund using installed-wheel `eac` + envassure[openenv].
# Does not require a flaky full OpenEnv HTTP server.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${ROOT}/.example-out"
mkdir -p "${OUT_DIR}"
cd "${ROOT}"

if ! command -v eac >/dev/null 2>&1; then
  echo "error: eac not on PATH (install the envassure wheel)" >&2
  exit 1
fi

for name in openenv.yaml world.json server/environment.py; do
  if [[ ! -e "${name}" ]]; then
    echo "error: missing scaffold member ${name}" >&2
    exit 1
  fi
done

echo "==> eac --version"
eac --version

echo "==> eac openenv test (deterministic reset + step; no HTTP)"
eac openenv test --dir . --json | tee "${OUT_DIR}/openenv-test.json"

echo "==> eac serve openenv smoke reset"
eac serve openenv --dir . --seed 0 --json | tee "${OUT_DIR}/openenv-serve.json"

echo "run.sh completed; artifacts under ${OUT_DIR}"
