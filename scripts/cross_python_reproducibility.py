#!/usr/bin/env python3
"""Build and compare cross-Python reproducibility evidence for one canonical .eap."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import sys
from pathlib import Path
from typing import Any

from envassure.canonical import canonical_hash
from envassure.packaging import PACK_MEMBER_PROVENANCE, load_pack, save_pack, verify_pack
from envassure.runtime import EventSourcedEnvironment

ROOT = Path(__file__).resolve().parents[1]
PACK_NAME = "counter-reproducibility.eap"
EVIDENCE_NAME = "evidence.json"


def _load_counter_world() -> Any:
    path = ROOT / "examples" / "counter" / "world.py"
    spec = importlib.util.spec_from_file_location("envassure_repro_counter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical world from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_counter_world()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_trace(world: Any) -> dict[str, Any]:
    env = EventSourcedEnvironment(world)
    reset_observation = env.reset(seed=42)
    steps: list[dict[str, Any]] = []
    for actor_id, action_id in [
        ("client", "increment"),
        ("client", "increment"),
        ("client", "get"),
    ]:
        result = env.step(actor_id, action_id)
        if not result.ok:
            raise RuntimeError(f"canonical runtime action failed: {actor_id}.{action_id}")
        steps.append(
            {
                "actor_id": actor_id,
                "action_id": action_id,
                "outcome": result.outcome.value,
                "events": [event.model_dump(mode="json") for event in result.events],
                "observation": result.observation,
                "state_digest": result.state_digest,
                "transaction": (
                    result.transaction.model_dump(mode="json")
                    if result.transaction is not None
                    else None
                ),
            }
        )
    snapshot = env.snapshot()
    return {
        "seed": 42,
        "reset_observation": reset_observation,
        "steps": steps,
        "final_state": env.state(),
        "final_state_digest": snapshot.digests.get("state"),
        "audit_head": snapshot.audit_head,
    }


def build_evidence(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    world = _load_counter_world()
    pack_path = output_dir / PACK_NAME
    manifest = save_pack(
        pack_path,
        world,
        metadata={"reproducibility_study": "py311-py312-v1"},
    )
    report = verify_pack(pack_path)
    diagnostics = [diag.model_dump(mode="json") for diag in report.diagnostics]
    if report.has_errors():
        raise RuntimeError(f"canonical pack failed verification: {diagnostics}")

    loaded_manifest, loaded_world, members = load_pack(pack_path)
    if loaded_manifest != manifest:
        raise RuntimeError("manifest changed across save/load")
    if loaded_world != world:
        raise RuntimeError("world changed across save/load")

    provenance = json.loads(members[PACK_MEMBER_PROVENANCE].decode("utf-8"))
    member_digests = {
        entry.path: {"sha256": entry.sha256, "size": entry.size}
        for entry in sorted(manifest.files, key=lambda item: item.path)
    }
    stable = {
        "schema_version": 1,
        "archive_sha256": _sha256_path(pack_path),
        "manifest": manifest.model_dump(mode="json"),
        "content_digest": manifest.content_digest,
        "member_digests": member_digests,
        "provenance_digest": canonical_hash(provenance),
        "provenance": provenance,
        "diagnostics": diagnostics,
        "runtime_trace": _runtime_trace(world),
    }
    evidence = {
        "stable": stable,
        "observed_platform": {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "allowed_platform_dependent_fields": ["observed_platform.python_version"],
        "evidence_digest": canonical_hash(stable),
    }
    evidence_path = output_dir / EVIDENCE_NAME
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evidence_path


def _load_evidence(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("stable"), dict):
        raise ValueError(f"invalid reproducibility evidence: {path}")
    return payload


def compare_evidence(left_path: Path, right_path: Path) -> None:
    left = _load_evidence(left_path)
    right = _load_evidence(right_path)

    expected_allowed = ["observed_platform.python_version"]
    if left.get("allowed_platform_dependent_fields") != expected_allowed:
        raise SystemExit(f"unexpected allowed-difference policy in {left_path}")
    if right.get("allowed_platform_dependent_fields") != expected_allowed:
        raise SystemExit(f"unexpected allowed-difference policy in {right_path}")

    left_platform = dict(left.get("observed_platform") or {})
    right_platform = dict(right.get("observed_platform") or {})
    left_version = left_platform.pop("python_version", None)
    right_version = right_platform.pop("python_version", None)
    if left_version == right_version:
        raise SystemExit("cross-Python comparison requires distinct interpreter versions")
    if left_platform != right_platform:
        raise SystemExit(
            "unexpected platform-dependent fields differ: "
            f"left={left_platform!r} right={right_platform!r}"
        )

    if left["stable"] != right["stable"]:
        differing = [
            key
            for key in sorted(set(left["stable"]) | set(right["stable"]))
            if left["stable"].get(key) != right["stable"].get(key)
        ]
        raise SystemExit(f"cross-Python reproducibility mismatch in stable fields: {differing}")
    if left.get("evidence_digest") != right.get("evidence_digest"):
        raise SystemExit("stable evidence digests differ")

    archive_sha = left["stable"].get("archive_sha256")
    if not isinstance(archive_sha, str) or len(archive_sha) != 64:
        raise SystemExit("archive SHA-256 is missing or malformed")
    print(
        json.dumps(
            {
                "status": "match",
                "python_versions": [left_version, right_version],
                "archive_sha256": archive_sha,
                "content_digest": left["stable"].get("content_digest"),
                "evidence_digest": left.get("evidence_digest"),
            },
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--output-dir", type=Path, required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("left", type=Path)
    compare.add_argument("right", type=Path)
    args = parser.parse_args()

    if args.command == "build":
        path = build_evidence(args.output_dir)
        print(path)
        return 0
    compare_evidence(args.left, args.right)
    return 0


if __name__ == "__main__":
    sys.exit(main())
