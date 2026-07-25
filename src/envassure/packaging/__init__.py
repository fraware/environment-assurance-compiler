"""Environment Pack (.eap) format: zip + manifest + checksums + secret scan."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from envassure.canonical import canonical_hash, sha256_hex
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import WorldDefinition
from envassure.ir.primitives import IR_VERSION

PACK_FORMAT_VERSION = "1"
PACK_MEMBER_MANIFEST = "manifest.json"
PACK_MEMBER_WORLD = "ir/world.json"

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
            "files": [f.model_dump(mode="json") for f in sorted(self.files, key=lambda e: e.path)],
        }
        self.content_digest = canonical_hash(payload)
        return self.content_digest


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


def build_pack_files(
    world: WorldDefinition,
    *,
    extra_files: dict[str, bytes | str] | None = None,
) -> dict[str, bytes]:
    """Assemble in-memory pack members (path → bytes), excluding manifest."""
    members: dict[str, bytes] = {
        PACK_MEMBER_WORLD: (json.dumps(world.model_dump(mode="json"), indent=2) + "\n").encode(
            "utf-8"
        ),
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
) -> PackManifest:
    """
    Write a ``.eap`` zip pack. Raises ``ValueError`` if secret scan fails.
    """
    members = build_pack_files(world, extra_files=extra_files)
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
    manifest = PackManifest(
        environment_id=world.environment_id,
        environment_version=world.version,
        created_at=datetime.now(UTC).isoformat(),
        files=files,
        metadata=metadata or {},
    )
    manifest.recompute_content_digest()
    manifest_bytes = (json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n").encode("utf-8")

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
    """Verify checksums, manifest digest, path safety, and optional secret scan."""
    report = DiagnosticReport(context={"pack": str(path)})
    try:
        with zipfile.ZipFile(path, "r") as zf:
            names = _safe_namelist(zf)
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
            expected = {e.path: e for e in manifest.files}
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
    if name.startswith("/") or name.startswith("\\") or ".." in name.split("/"):
        raise ValueError(f"unsafe pack member path: {name}")
    if Path(name).is_absolute():
        raise ValueError(f"absolute pack member path forbidden: {name}")


def _safe_namelist(zf: zipfile.ZipFile) -> list[str]:
    names = zf.namelist()
    for name in names:
        _assert_safe_member(name)
    return names


def pack_schema() -> dict[str, Any]:
    schema = PackManifest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://envassure.dev/schemas/pack-manifest-{PACK_FORMAT_VERSION}.json"
    schema["title"] = "PackManifest"
    return schema


def export_pack_schema(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"pack-manifest-{PACK_FORMAT_VERSION}.json"
    path.write_text(json.dumps(pack_schema(), indent=2) + "\n", encoding="utf-8")
    latest = directory / "pack-manifest.json"
    latest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path
