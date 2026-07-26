#!/usr/bin/env bash
# Resolve a working Python for example scripts.
# Prefer `python` then `python3`, and require a real interpreter (skip Windows
# Store stubs that exist on PATH but exit non-zero).
PYTHON_BIN=""
for candidate in python python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c "import sys" >/dev/null 2>&1; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "error: python/python3 not usable on PATH" >&2
  exit 1
fi
export PYTHON_BIN
