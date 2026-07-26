#!/usr/bin/env bash
# Verify a frozen EnvAssure reproducibility bundle without needing the git checkout.
# Expectation: this script runs from the extracted bundle root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -f MANIFEST.json ]]; then
  echo "MANIFEST.json missing" >&2
  exit 1
fi
if [[ ! -f expected-digests.json ]]; then
  echo "expected-digests.json missing" >&2
  exit 1
fi

python3 - <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(".")
manifest = json.loads((root / "MANIFEST.json").read_text(encoding="utf-8"))
expected = json.loads((root / "expected-digests.json").read_text(encoding="utf-8"))

errors: list[str] = []

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

for entry in manifest.get("files", []):
    rel = entry["path"]
    path = root / rel
    if not path.is_file():
        errors.append(f"missing file listed in MANIFEST: {rel}")
        continue
    actual = sha256(path)
    if actual != entry["sha256"]:
        errors.append(f"MANIFEST digest mismatch for {rel}: {actual} != {entry['sha256']}")

for rel, digest in expected.get("files", {}).items():
    path = root / rel
    if not path.is_file():
        errors.append(f"missing expected digest file: {rel}")
        continue
    actual = sha256(path)
    if actual != digest:
        errors.append(f"expected-digests mismatch for {rel}: {actual} != {digest}")

bundle_digest = expected.get("bundle_digest")
if bundle_digest:
    # Bundle digest covers MANIFEST.json file list order + digests (not recursive rehash of all bytes).
    payload = [{"path": e["path"], "sha256": e["sha256"]} for e in manifest.get("files", [])]
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=False).encode()
    # Prefer canonical: sort by path
    payload_sorted = sorted(payload, key=lambda x: x["path"])
    encoded = json.dumps(payload_sorted, separators=(",", ":")).encode()
    actual_bundle = hashlib.sha256(encoded).hexdigest()
    if actual_bundle != bundle_digest:
        errors.append(f"bundle_digest mismatch: {actual_bundle} != {bundle_digest}")

if errors:
    print("VERIFY FAILED", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    sys.exit(1)

print("VERIFY OK")
print(f"files={len(manifest.get('files', []))}")
print(f"bundle_digest={bundle_digest}")
PY
