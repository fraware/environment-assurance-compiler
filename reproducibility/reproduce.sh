#!/usr/bin/env bash
# Rebuild / refresh local reproduce artifacts when a source checkout is available.
# For clean-room verification use verify.sh on a published bundle artifact.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$ROOT/.." && pwd)"

cd "$REPO_ROOT"
export PYTHONPATH="${PYTHONPATH:-}:src"

echo "==> lint + verify benchmark packs"
python -c "from envassure.cli.main import app; import sys; sys.argv=['eac','pack','verify','packs','--json']; app()"

echo "==> refresh reproducibility digests"
python scripts/generate_reproducibility_bundle.py --refresh

echo "==> verify bundle in place"
bash "$ROOT/verify.sh"

echo "REPRODUCE OK"
