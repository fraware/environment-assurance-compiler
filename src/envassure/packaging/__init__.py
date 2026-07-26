"""Environment Pack (.eap) format v2: zip + manifest + checksums + secret scan."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from envassure import __version__ as PACKAGE_VERSION
from envassure.canonical import canonical_hash, sha256_hex
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.fidelity.ledger import FidelityLedger, ledger_from_world
from envassure.ir.models import WorldDefinition
from envassure.ir.primitives import IR_PRIOR_STABLE, IR_VERSION, SUPPORTED_READ_VERSIONS
from envassure.ir.schema import world_json_schema

PACK_FORMAT_VERSION = "2"
PACK_PRIOR_STABLE = "1"
SUPPORTED_PACK_READ_VERSIONS: frozenset[str] = frozenset({PACK_FORMAT_VERSION})

PACK_MEMBER_MANIFEST = "manifest.json"
PACK_MEMBER_WORLD = "ir/world.json"
PACK_MEMBER_SOURCES = "sources/manifest.json"
PACK_MEMBER_PROVENANCE = "provenance/bundle.json"
PACK_MEMBER_MIGRATION = "migration/history.json"
PACK_MEMBER_COMPATIBILITY = "compatibility.json"
PACK_MEMBER_FIDELITY = "fidelity/ledger.json"
PACK_MEMBER_WORLD_SCHEMA = f"schemas/world-{IR_VERSION}.json"
PACK_MEMBER_WORLD_SCHEMA_ALIAS = "schemas/world.json"
PACK_MEMBER_PACK_SCHEMA = f"schemas/pack-manifest-{PACK_FORMAT_VERSION}.json"
PACK_MEMBER_PACK_SCHEMA_ALIAS = "schemas/pack-manifest.json"

REQUIRED_PACK_MEMBERS: frozenset[str] = frozenset(
    {
        PACK_MEMBER_WORLD,
        PACK_MEMBER_SOURCES,
        PACK_MEMBER_PROVENANCE,
        PACK_MEMBER_MIGRATION,
        PACK_MEMBER_COMPATIBILITY,
        PACK_MEMBER_FIDELITY,
        PACK_MEMBER_WORLD_SCHEMA,
        PACK_MEMBER_WORLD_SCHEMA_ALIAS,
        PACK_MEMBER_PACK_SCHEMA,
        PACK_MEMBER_PACK_SCHEMA_ALIAS,
    }
)

# Decompression bomb limits (fail closed).
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
MAX_MEMBER_COUNT = 10_000

# Simple secret patterns (gate, not a full DLP product).
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "aws_secret_access_key",
        re.compile(r"(?i)aws(.{0,20})?(secret|access).{0,20}['\"][0-9a-zA-Z/+]{40}['\"]"),
    ),
    (
        "password_assignment",
        re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    ),
    (
        "generic_api_key",
        re.compile(r"(?i)(api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][0-9a-zA-Z_\-]{16,}['\"]"),
    ),
)


class PackFileEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str
    size: int


class PackManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: str = PACK_FORMAT_VERSION
    environment_id: str
    environment_version: str
    ir_version: str = IR_VERSION
    runtime_version: str = PACKAGE_VERSION
    policy_version: str = ""
    created_at: str
    files: list[PackFileEntry] = Field(default_factory=list)
    content_digest: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def recompute_content_digest(self) -> str:
        payload = {
            "format_version": self.format_version,
            "environment_id": self.environment_id,
            "environment_version": self.environment_version,
            "ir_version": self.ir_version,
            "runtime_version": self.runtime_version,
            "policy_version": self.policy_version,
            "files": [f.model_dump(mode="json") for f in sorted(self.files, key=lambda e: e.path)],
        }
        self.content_digest = canonical_hash(payload)
        return self.content_digest


def policy_version_for_world(world: WorldDefinition) -> str:
    """Stable digest of authorization / failure policy relevant to the pack."""
    return canonical_hash(
        {
            "assurance_profile": world.assurance_profile,
            "authorization": [a.authorization for a in world.actions],
            "failures": [f.model_dump(mode="json") for f in world.failures],
        }
    )


def pack_compatibility_document() -> dict[str, Any]:
    return {
        "pack_format_version": PACK_FORMAT_VERSION,
        "supported_pack_read_versions": sorted(SUPPORTED_PACK_READ_VERSIONS),
        "pack_prior_stable": PACK_PRIOR_STABLE,
        "ir_version": IR_VERSION,
        "supported_ir_read_versions": sorted(SUPPORTED_READ_VERSIONS),
        "ir_prior_stable": IR_PRIOR_STABLE,
        "runtime_version": PACKAGE_VERSION,
    }


def build_provenance_bundle(world: WorldDefinition) -> dict[str, Any]:
    """Flatten IR provenance (+ ambiguity decision links) for pack embedding."""
    elements: list[dict[str, Any]] = []

    def _add(kind: str, element_id: str, provenance: Any) -> None:
        elements.append(
            {
                "kind": kind,
                "id": element_id,
                "provenance": provenance.model_dump(mode="json"),
            }
        )

    _add("world", world.environment_id, world.provenance)
    for state in world.state:
        _add("state", state.id, state.provenance)
    for actor in world.actors:
        _add("actor", actor.id, actor.provenance)
    for observation in world.observations:
        _add("observation", observation.id, observation.provenance)
    for action in world.actions:
        _add("action", action.id, action.provenance)
    for failure in world.failures:
        _add("failure", failure.id, failure.provenance)
    for transition in world.transitions:
        _add("transition", transition.id, transition.provenance)
    for task in world.tasks:
        _add("task", task.id, task.provenance)
    for verifier in world.verifiers:
        _add("verifier", verifier.id, verifier.provenance)
    for obligation in world.evidence_obligations:
        _add("evidence_obligation", obligation.id, obligation.provenance)
    decisions: list[dict[str, Any]] = []
    for ambiguity in world.ambiguities:
        _add("ambiguity", ambiguity.id, ambiguity.provenance)
        if ambiguity.provenance.decision_ids:
            decisions.append(
                {
                    "ambiguity_id": ambiguity.id,
                    "decision_ids": list(ambiguity.provenance.decision_ids),
                    "status": ambiguity.status,
                }
            )
    return {
        "environment_id": world.environment_id,
        "ir_version": world.ir_version,
        "elements": elements,
        "decisions": decisions,
    }


def build_migration_history(
    world: WorldDefinition,
    *,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if history is not None:
        return history
    return {
        "from_version": world.ir_version,
        "to_version": world.ir_version,
        "steps": [],
        "notes": ["identity; no migration applied at pack time"],
    }


def build_sources_manifest_payload(
    world: WorldDefinition,
    *,
    sources_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if sources_manifest is not None:
        payload = dict(sources_manifest)
        payload.setdefault("environment_id", world.environment_id)
        return payload
    entries = [
        {"source_id": sid, "digest": None, "note": "declared on world.semantic_sources only"}
        for sid in world.semantic_sources
    ]
    return {
        "schema_version": 1,
        "environment_id": world.environment_id,
        "sources": entries,
        "notes": [
            "No workspace sources.yml supplied at pack time; "
            "entries reflect world.semantic_sources ids only."
        ],
    }


def load_sources_manifest_for_pack(path: Path) -> dict[str, Any]:
    """Load ``sources.yml`` / YAML or JSON into the pack ``sources/manifest.json`` payload."""
    suffix = path.suffix.lower()
    if suffix in {".yml", ".yaml"}:
        # Local import keeps packaging usable when workspace helpers are unused.
        from envassure.workspace.sources import load_sources_manifest

        manifest = load_sources_manifest(path)
        return {
            "schema_version": manifest.schema_version,
            "sources": [s.model_dump(mode="json") for s in manifest.sources],
            "notes": [f"Embedded from workspace sources manifest {path.name}"],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"sources manifest at {path} must be a JSON object")
    return data


def load_migration_history_for_pack(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"migration history at {path} must be a JSON object")
    return data


def signature_pack_members(paths: list[Path]) -> dict[str, bytes]:
    """Map detached signature files into ``signatures/<filename>`` pack members."""
    members: dict[str, bytes] = {}
    for path in paths:
        if not path.is_file():
            raise ValueError(f"signature file not found: {path}")
        rel = f"signatures/{path.name}"
        if rel in members:
            raise ValueError(f"duplicate signature member name: {rel}")
        members[rel] = path.read_bytes()
    return members


def signature_integrity_metadata(members: dict[str, bytes]) -> dict[str, Any] | None:
    """Build integrity metadata for optional ``signatures/`` members (no crypto).

    Records per-signature SHA-256 digests and a ``signed_content_digest`` over all
    non-signature pack members so verify can fail closed on orphan or mismatched
    signature inventory without inventing key verification.
    """
    signature_entries: list[dict[str, Any]] = []
    content_parts: list[dict[str, str]] = []
    for rel, data in sorted(members.items()):
        digest = sha256_hex(data)
        if rel.startswith("signatures/"):
            signature_entries.append({"path": rel, "sha256": digest, "size": len(data)})
        else:
            content_parts.append({"path": rel, "sha256": digest})
    if not signature_entries:
        return None
    return {
        "scheme": "detached-opaque-v1",
        "note": (
            "Integrity listing only: signature bytes are hashed and bound to "
            "non-signature member digests. Cryptographic verification requires "
            "an external verifier and is out of band."
        ),
        "members": signature_entries,
        "signed_content_digest": canonical_hash(content_parts),
    }


def scan_secrets(text: str, *, path: str = "<memory>") -> list[tuple[str, str]]:
    """Return list of (pattern_name, path) for suspected secrets."""
    hits: list[tuple[str, str]] = []
    for name, pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            hits.append((name, path))
    return hits


def scan_path_for_secrets(root: Path) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip", ".eap"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        hits.extend(scan_secrets(text, path=rel))
    return hits


def _json_bytes(payload: dict[str, Any] | list[Any]) -> bytes:
    return (json.dumps(payload, indent=2) + "\n").encode("utf-8")


def build_pack_files(
    world: WorldDefinition,
    *,
    extra_files: dict[str, bytes | str] | None = None,
    fidelity_ledger: FidelityLedger | None = None,
    sources_manifest: dict[str, Any] | None = None,
    migration_history: dict[str, Any] | None = None,
) -> dict[str, bytes]:
    """Assemble in-memory pack members (path → bytes), excluding manifest."""
    ledger = fidelity_ledger or ledger_from_world(world)
    if ledger.environment_id != world.environment_id:
        raise ValueError(
            f"fidelity ledger environment_id {ledger.environment_id!r} "
            f"does not match world {world.environment_id!r}"
        )

    pack_schema_doc = pack_schema()
    members: dict[str, bytes] = {
        PACK_MEMBER_WORLD: _json_bytes(world.model_dump(mode="json")),
        PACK_MEMBER_WORLD_SCHEMA: _json_bytes(world_json_schema()),
        PACK_MEMBER_WORLD_SCHEMA_ALIAS: _json_bytes(world_json_schema()),
        PACK_MEMBER_PACK_SCHEMA: _json_bytes(pack_schema_doc),
        PACK_MEMBER_PACK_SCHEMA_ALIAS: _json_bytes(pack_schema_doc),
        PACK_MEMBER_SOURCES: _json_bytes(
            build_sources_manifest_payload(world, sources_manifest=sources_manifest)
        ),
        PACK_MEMBER_PROVENANCE: _json_bytes(build_provenance_bundle(world)),
        PACK_MEMBER_MIGRATION: _json_bytes(
            build_migration_history(world, history=migration_history)
        ),
        PACK_MEMBER_COMPATIBILITY: _json_bytes(pack_compatibility_document()),
        PACK_MEMBER_FIDELITY: ledger.to_pack_member(),
    }
    for rel, content in (extra_files or {}).items():
        norm = _normalize_member_path(rel)
        if isinstance(content, str):
            members[norm] = content.encode("utf-8")
        else:
            members[norm] = content
    return members


def save_pack(
    path: Path,
    world: WorldDefinition,
    *,
    extra_files: dict[str, bytes | str] | None = None,
    metadata: dict[str, Any] | None = None,
    secret_scan: bool = True,
    fidelity_ledger: FidelityLedger | None = None,
    sources_manifest: dict[str, Any] | None = None,
    migration_history: dict[str, Any] | None = None,
    runtime_version: str | None = None,
    policy_version: str | None = None,
) -> PackManifest:
    """
    Write a ``.eap`` zip pack (format v2). Raises ``ValueError`` if secret scan fails.
    """
    members = build_pack_files(
        world,
        extra_files=extra_files,
        fidelity_ledger=fidelity_ledger,
        sources_manifest=sources_manifest,
        migration_history=migration_history,
    )
    if secret_scan:
        for rel, data in members.items():
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            hits = scan_secrets(text, path=rel)
            if hits:
                names = ", ".join(sorted({h[0] for h in hits}))
                raise ValueError(f"secret scan failed in {rel}: {names}")

    files: list[PackFileEntry] = []
    for rel, data in sorted(members.items()):
        files.append(PackFileEntry(path=rel, sha256=sha256_hex(data), size=len(data)))
    meta = dict(metadata or {})
    sig_meta = signature_integrity_metadata(members)
    if sig_meta is not None:
        meta["signatures"] = sig_meta
    manifest = PackManifest(
        environment_id=world.environment_id,
        environment_version=world.version,
        ir_version=world.ir_version,
        runtime_version=runtime_version or PACKAGE_VERSION,
        policy_version=policy_version or policy_version_for_world(world),
        created_at=datetime.now(UTC).isoformat(),
        files=files,
        metadata=meta,
    )
    manifest.recompute_content_digest()
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PACK_MEMBER_MANIFEST, manifest_bytes)
        for rel, data in sorted(members.items()):
            _assert_safe_member(rel)
            zf.writestr(rel, data)
    return manifest


def load_pack(path: Path) -> tuple[PackManifest, WorldDefinition, dict[str, bytes]]:
    """Load pack manifest, world IR, and raw members (excluding manifest)."""
    with zipfile.ZipFile(path, "r") as zf:
        _safe_namelist(zf)
        _enforce_decompression_limits(zf)
        manifest = PackManifest.model_validate(
            json.loads(zf.read(PACK_MEMBER_MANIFEST).decode("utf-8"))
        )
        members: dict[str, bytes] = {}
        for name in zf.namelist():
            if name == PACK_MEMBER_MANIFEST or name.endswith("/"):
                continue
            members[name] = zf.read(name)
        if PACK_MEMBER_WORLD not in members:
            raise ValueError(f"pack missing {PACK_MEMBER_WORLD}")
        world = WorldDefinition.model_validate(
            json.loads(members[PACK_MEMBER_WORLD].decode("utf-8"))
        )
    return manifest, world, members


def verify_pack(path: Path, *, secret_scan: bool = True) -> DiagnosticReport:
    """Verify format window, required members, checksums, path safety, secrets."""
    report = DiagnosticReport(context={"pack": str(path)})
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = _safe_namelist(zf)
            _reject_duplicate_names(names, report)
            if report.has_errors():
                return report
            _enforce_decompression_limits(zf, report=report)
            if report.has_errors():
                return report
            if PACK_MEMBER_MANIFEST not in names:
                report.add(
                    make_diagnostic(
                        "EAC8006",
                        reason="missing manifest.json",
                        subject=str(path),
                    )
                )
                return report
            manifest = PackManifest.model_validate(
                json.loads(zf.read(PACK_MEMBER_MANIFEST).decode("utf-8"))
            )
            if manifest.format_version not in SUPPORTED_PACK_READ_VERSIONS:
                report.add(
                    make_diagnostic(
                        "EAC8006",
                        reason=(
                            f"unsupported format_version {manifest.format_version!r}; "
                            f"supported={sorted(SUPPORTED_PACK_READ_VERSIONS)}"
                        ),
                        subject=str(path),
                    )
                )
                return report
            if manifest.ir_version not in SUPPORTED_READ_VERSIONS:
                report.add(
                    make_diagnostic(
                        "EAC8006",
                        reason=(
                            f"unsupported ir_version {manifest.ir_version!r}; "
                            f"supported={sorted(SUPPORTED_READ_VERSIONS)}"
                        ),
                        subject=str(path),
                    )
                )
            if not manifest.runtime_version:
                report.add(
                    make_diagnostic(
                        "EAC8006",
                        reason="manifest missing runtime_version",
                        subject=str(path),
                    )
                )
            if not manifest.policy_version:
                report.add(
                    make_diagnostic(
                        "EAC8006",
                        reason="manifest missing policy_version",
                        subject=str(path),
                    )
                )

            member_set = {n for n in names if not n.endswith("/") and n != PACK_MEMBER_MANIFEST}
            for required in sorted(REQUIRED_PACK_MEMBERS):
                if required not in member_set:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"missing required member {required}",
                            subject=required,
                        )
                    )

            # Optional signatures/: if present, each file must be hashed in the manifest.
            signature_members = sorted(n for n in member_set if n.startswith("signatures/"))
            expected = {e.path: e for e in manifest.files}
            for sig in signature_members:
                if sig not in expected:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"signature member {sig} not listed in manifest.files",
                            subject=sig,
                        )
                    )
            # Manifest-listed signature paths must exist in the ZIP (orphan listing).
            for entry_path in sorted(expected):
                if entry_path.startswith("signatures/") and entry_path not in member_set:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=(
                                f"manifest lists signature {entry_path} but ZIP member "
                                "is missing (orphan signature listing)"
                            ),
                            subject=entry_path,
                        )
                    )

            # Integrity metadata (when present) must match signature inventory + digests.
            sig_meta = manifest.metadata.get("signatures") if manifest.metadata else None
            if signature_members or sig_meta is not None:
                if not isinstance(sig_meta, dict):
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=(
                                "signatures present but manifest.metadata.signatures "
                                "integrity block is missing or not an object"
                            ),
                            subject=str(path),
                        )
                    )
                else:
                    listed = sig_meta.get("members")
                    if not isinstance(listed, list):
                        report.add(
                            make_diagnostic(
                                "EAC8006",
                                reason="metadata.signatures.members must be a list",
                                subject=str(path),
                            )
                        )
                    else:
                        meta_paths = []
                        for item in listed:
                            if not isinstance(item, dict):
                                report.add(
                                    make_diagnostic(
                                        "EAC8006",
                                        reason="metadata.signatures.members entry must be an object",
                                        subject=str(path),
                                    )
                                )
                                continue
                            mpath = item.get("path")
                            mdigest = item.get("sha256")
                            msize = item.get("size")
                            if not isinstance(mpath, str) or not isinstance(mdigest, str):
                                report.add(
                                    make_diagnostic(
                                        "EAC8006",
                                        reason=(
                                            "metadata.signatures.members entries require "
                                            "string path and sha256"
                                        ),
                                        subject=str(path),
                                    )
                                )
                                continue
                            meta_paths.append(mpath)
                            if mpath not in member_set:
                                report.add(
                                    make_diagnostic(
                                        "EAC8006",
                                        reason=(f"metadata signature {mpath} missing from pack"),
                                        subject=mpath,
                                    )
                                )
                                continue
                            data = zf.read(mpath)
                            actual = sha256_hex(data)
                            if actual != mdigest:
                                report.add(
                                    make_diagnostic(
                                        "EAC8006",
                                        reason=(
                                            f"signature digest mismatch for {mpath}: "
                                            f"metadata {mdigest}, actual {actual}"
                                        ),
                                        subject=mpath,
                                    )
                                )
                            if isinstance(msize, int) and msize != len(data):
                                report.add(
                                    make_diagnostic(
                                        "EAC8006",
                                        reason=f"signature size mismatch for {mpath}",
                                        subject=mpath,
                                    )
                                )
                            file_entry = expected.get(mpath)
                            if file_entry is not None and file_entry.sha256 != mdigest:
                                report.add(
                                    make_diagnostic(
                                        "EAC8006",
                                        reason=(
                                            f"signature {mpath} metadata sha256 disagrees "
                                            "with manifest.files"
                                        ),
                                        subject=mpath,
                                    )
                                )
                        if sorted(meta_paths) != signature_members:
                            report.add(
                                make_diagnostic(
                                    "EAC8006",
                                    reason=(
                                        "metadata.signatures.members paths do not match "
                                        f"ZIP signatures/ inventory: "
                                        f"meta={sorted(meta_paths)} zip={signature_members}"
                                    ),
                                    subject=str(path),
                                )
                            )
                    declared_content = sig_meta.get("signed_content_digest")
                    if isinstance(declared_content, str) and declared_content:
                        content_parts = [
                            {
                                "path": rel,
                                "sha256": sha256_hex(zf.read(rel)),
                            }
                            for rel in sorted(member_set)
                            if not rel.startswith("signatures/")
                        ]
                        actual_content = canonical_hash(content_parts)
                        if actual_content != declared_content:
                            report.add(
                                make_diagnostic(
                                    "EAC8006",
                                    reason=(
                                        "signed_content_digest mismatch: signature "
                                        "metadata no longer binds non-signature members"
                                    ),
                                    subject=str(path),
                                )
                            )

            for entry in manifest.files:
                if entry.path not in names:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"missing member {entry.path}",
                            subject=entry.path,
                        )
                    )
                    continue
                data = zf.read(entry.path)
                digest = sha256_hex(data)
                if digest != entry.sha256:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=(
                                f"checksum mismatch for {entry.path}: "
                                f"expected {entry.sha256}, got {digest}"
                            ),
                            subject=entry.path,
                        )
                    )
                if len(data) != entry.size:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"size mismatch for {entry.path}",
                            subject=entry.path,
                        )
                    )
                if secret_scan:
                    try:
                        text = data.decode("utf-8")
                    except UnicodeDecodeError:
                        text = ""
                    for pattern_name, _ in scan_secrets(text, path=entry.path):
                        report.add(
                            make_diagnostic(
                                "EAC8006",
                                reason=f"secret pattern {pattern_name!r} in {entry.path}",
                                subject=entry.path,
                            )
                        )
            # Unexpected members (except directories)
            for name in names:
                if name == PACK_MEMBER_MANIFEST or name.endswith("/"):
                    continue
                if name not in expected:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"unexpected member {name}",
                            subject=name,
                        )
                    )
            # Content digest
            check = manifest.model_copy(deep=True)
            check.recompute_content_digest()
            if check.content_digest != manifest.content_digest:
                report.add(
                    make_diagnostic(
                        "EAC8006",
                        reason="manifest content_digest mismatch",
                        subject=str(path),
                    )
                )
            # Compatibility member must agree with declared window when present.
            if PACK_MEMBER_COMPATIBILITY in member_set:
                try:
                    compat = json.loads(zf.read(PACK_MEMBER_COMPATIBILITY).decode("utf-8"))
                    declared = set(compat.get("supported_pack_read_versions") or [])
                    if declared and manifest.format_version not in declared:
                        report.add(
                            make_diagnostic(
                                "EAC8006",
                                reason=(
                                    f"format_version {manifest.format_version!r} outside "
                                    f"compatibility.json window {sorted(declared)}"
                                ),
                                subject=PACK_MEMBER_COMPATIBILITY,
                            )
                        )
                except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"invalid compatibility.json: {exc}",
                            subject=PACK_MEMBER_COMPATIBILITY,
                        )
                    )

            # Required structured members must parse; fidelity ledger is schema-validated.
            # IR world must validate; provenance must cover the environment id.
            world_for_checks: WorldDefinition | None = None
            if PACK_MEMBER_WORLD in member_set:
                try:
                    world_for_checks = WorldDefinition.model_validate(
                        json.loads(zf.read(PACK_MEMBER_WORLD).decode("utf-8"))
                    )
                    if world_for_checks.environment_id != manifest.environment_id:
                        report.add(
                            make_diagnostic(
                                "EAC8006",
                                reason=(
                                    f"ir/world.json environment_id "
                                    f"{world_for_checks.environment_id!r} does not match "
                                    f"manifest {manifest.environment_id!r}"
                                ),
                                subject=PACK_MEMBER_WORLD,
                            )
                        )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    ValueError,
                    ValidationError,
                ) as exc:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"invalid ir/world.json: {exc}",
                            subject=PACK_MEMBER_WORLD,
                        )
                    )
            for member, label in (
                (PACK_MEMBER_SOURCES, "sources manifest"),
                (PACK_MEMBER_PROVENANCE, "provenance bundle"),
                (PACK_MEMBER_MIGRATION, "migration history"),
            ):
                if member not in member_set:
                    continue
                try:
                    payload = json.loads(zf.read(member).decode("utf-8"))
                    if not isinstance(payload, dict):
                        raise ValueError(f"{label} root must be a JSON object")
                    if member == PACK_MEMBER_PROVENANCE:
                        elements = payload.get("elements")
                        if not isinstance(elements, list) or not elements:
                            raise ValueError("provenance bundle elements must be a non-empty list")
                        env_ids = {
                            e.get("id")
                            for e in elements
                            if isinstance(e, dict) and e.get("kind") == "world"
                        }
                        if (
                            world_for_checks is not None
                            and world_for_checks.environment_id not in env_ids
                        ):
                            raise ValueError(
                                "provenance bundle missing world element for "
                                f"{world_for_checks.environment_id!r}"
                            )
                        if (
                            payload.get("environment_id")
                            and world_for_checks is not None
                            and payload["environment_id"] != world_for_checks.environment_id
                        ):
                            raise ValueError(
                                "provenance environment_id does not match ir/world.json"
                            )
                    if member == PACK_MEMBER_SOURCES:
                        sources = payload.get("sources")
                        if sources is not None and not isinstance(sources, list):
                            raise ValueError("sources manifest sources must be a list")
                        if isinstance(sources, list):
                            for entry in sources:
                                if not isinstance(entry, dict):
                                    raise ValueError("sources entry must be an object")
                                if "source_id" not in entry:
                                    raise ValueError("sources entry missing source_id")
                    if member == PACK_MEMBER_MIGRATION:
                        if "from_version" not in payload or "to_version" not in payload:
                            raise ValueError(
                                "migration history requires from_version and to_version"
                            )
                        steps = payload.get("steps")
                        if steps is not None and not isinstance(steps, list):
                            raise ValueError("migration history steps must be a list")
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"invalid {label}: {exc}",
                            subject=member,
                        )
                    )
            if PACK_MEMBER_FIDELITY in member_set:
                try:
                    ledger = FidelityLedger.model_validate(
                        json.loads(zf.read(PACK_MEMBER_FIDELITY).decode("utf-8"))
                    )
                    if ledger.environment_id != manifest.environment_id:
                        report.add(
                            make_diagnostic(
                                "EAC8006",
                                reason=(
                                    f"fidelity ledger environment_id "
                                    f"{ledger.environment_id!r} does not match "
                                    f"manifest {manifest.environment_id!r}"
                                ),
                                subject=PACK_MEMBER_FIDELITY,
                            )
                        )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                    ValueError,
                    ValidationError,
                ) as exc:
                    report.add(
                        make_diagnostic(
                            "EAC8006",
                            reason=f"invalid fidelity ledger: {exc}",
                            subject=PACK_MEMBER_FIDELITY,
                        )
                    )
    except (OSError, zipfile.BadZipFile, ValueError, KeyError) as exc:
        report.add(
            make_diagnostic(
                "EAC8006",
                reason=str(exc),
                subject=str(path),
            )
        )
    return report


def _normalize_member_path(rel: str) -> str:
    norm = rel.replace("\\", "/").lstrip("/")
    _assert_safe_member(norm)
    return norm


def _assert_safe_member(name: str) -> None:
    if not name or name.endswith("/"):
        # Directory placeholders are allowed in namelist checks elsewhere.
        if name.endswith("/"):
            stripped = name.rstrip("/")
            if stripped:
                _assert_safe_member(stripped)
            return
        raise ValueError(f"unsafe pack member path: {name!r}")
    if name.startswith("/") or name.startswith("\\") or ".." in name.split("/"):
        raise ValueError(f"unsafe pack member path: {name}")
    if Path(name).is_absolute():
        raise ValueError(f"absolute pack member path forbidden: {name}")
    # Reject Windows drive-like prefixes and backslash escapes.
    if re.match(r"^[A-Za-z]:", name) or "\\" in name:
        raise ValueError(f"unsafe pack member path: {name}")


def _safe_namelist(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    for name in names:
        _assert_safe_member(name)
    return names


def _reject_duplicate_names(names: list[str], report: DiagnosticReport) -> None:
    seen: set[str] = set()
    for name in names:
        if name in seen:
            report.add(
                make_diagnostic(
                    "EAC8006",
                    reason=f"duplicate ZIP entry name {name!r}",
                    subject=name,
                )
            )
        seen.add(name)


def _enforce_decompression_limits(
    zf: zipfile.ZipFile,
    *,
    report: DiagnosticReport | None = None,
) -> None:
    infos = zf.infolist()
    if len(infos) > MAX_MEMBER_COUNT:
        msg = f"too many ZIP members: {len(infos)} > {MAX_MEMBER_COUNT}"
        if report is not None:
            report.add(make_diagnostic("EAC8006", reason=msg, subject="<archive>"))
            return
        raise ValueError(msg)
    total_uncompressed = 0
    for info in infos:
        if info.is_dir():
            continue
        uncompressed = int(info.file_size)
        compressed = max(int(info.compress_size), 1)
        total_uncompressed += uncompressed
        if uncompressed > MAX_UNCOMPRESSED_BYTES:
            msg = (
                f"member {info.filename!r} uncompressed size {uncompressed} "
                f"exceeds limit {MAX_UNCOMPRESSED_BYTES}"
            )
            if report is not None:
                report.add(make_diagnostic("EAC8006", reason=msg, subject=info.filename))
            else:
                raise ValueError(msg)
            continue
        ratio = uncompressed / compressed
        if ratio > MAX_COMPRESSION_RATIO and uncompressed > 1024 * 1024:
            msg = (
                f"member {info.filename!r} compression ratio {ratio:.1f} "
                f"exceeds limit {MAX_COMPRESSION_RATIO}"
            )
            if report is not None:
                report.add(make_diagnostic("EAC8006", reason=msg, subject=info.filename))
            else:
                raise ValueError(msg)
    if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
        msg = f"total uncompressed size {total_uncompressed} exceeds limit {MAX_UNCOMPRESSED_BYTES}"
        if report is not None:
            report.add(make_diagnostic("EAC8006", reason=msg, subject="<archive>"))
        else:
            raise ValueError(msg)


def pack_schema() -> dict[str, Any]:
    schema = PackManifest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://envassure.dev/schemas/pack-manifest-{PACK_FORMAT_VERSION}.json"
    schema["title"] = "PackManifest"
    schema["x-envassure-pack-format-version"] = PACK_FORMAT_VERSION
    schema["x-envassure-supported-pack-read-versions"] = sorted(SUPPORTED_PACK_READ_VERSIONS)
    return schema


def export_pack_schema(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"pack-manifest-{PACK_FORMAT_VERSION}.json"
    path.write_text(json.dumps(pack_schema(), indent=2) + "\n", encoding="utf-8")
    latest = directory / "pack-manifest.json"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def write_raw_zip(path: Path, members: dict[str, bytes], *, compress: bool = True) -> None:
    """Test helper: write an arbitrary ZIP without going through save_pack."""
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=compression) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
