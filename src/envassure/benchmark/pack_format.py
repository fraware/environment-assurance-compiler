"""Benchmark pack format (pack.yaml) — distinct from Environment Pack (.eap).

Layout and fields follow the public-beta engineering spec §10.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from envassure.canonical import canonical_hash, sha256_hex
from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport
from envassure.ir.models import WorldDefinition
from envassure.packaging import scan_path_for_secrets

BENCHMARK_PACK_SCHEMA_VERSION = "1"

REQUIRED_ROOT_FILES: frozenset[str] = frozenset(
    {
        "pack.yaml",
        "LICENSE",
        "README.md",
        "data-card.md",
        "benchmark-card.md",
    }
)

REQUIRED_DIRS: frozenset[str] = frozenset(
    {
        "sources",
        "decisions",
        "world",
        "tasks",
        "probes",
        "baselines",
        "expected-public",
        "schemas",
    }
)

INCLUDE_KEYS: tuple[str, ...] = (
    "source_conflict",
    "open_ambiguity",
    "hidden_reference",
    "unsupported_uses",
    "baseline",
    "mutation_suite",
    "differential_plan",
)

PermittedUse = Literal[
    "research",
    "evaluation",
    "education",
    "benchmarking",
    "development",
]
Sensitivity = Literal["public", "internal", "restricted"]
ConnectorType = Literal["fixture_oracle", "in_memory", "http", "none"]
MetricName = Literal[
    "transition_agreement",
    "auth_agreement",
    "failure_agreement",
    "observation_agreement",
    "leakage",
    "solvability",
    "diff_match",
    "solve_rate",
    "verify_fpr",
]


class PackMaintainer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    email: str | None = None
    role: str | None = None


class PackDigests(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hidden_oracle: str
    baseline_world: str | None = None
    pack_tree: str | None = None


class PackIncludes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_conflict: str
    open_ambiguity: str
    hidden_reference: str
    unsupported_uses: str
    baseline: str
    mutation_suite: str
    differential_plan: str


class BenchmarkPackManifest(BaseModel):
    """Validated ``pack.yaml`` document (schema_version 1)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    pack_id: str
    version: str
    name: str | None = None
    description: str | None = None
    domain: str
    licenses: list[str] = Field(min_length=1)
    permitted_uses: list[PermittedUse] = Field(min_length=1)
    sensitivity: Sensitivity
    required_envassure: str
    required_ir: str
    connector_type: ConnectorType
    workflow_id: str | None = None
    public_components: list[str] = Field(min_length=1)
    hidden_components: list[str] = Field(min_length=1)
    probe_families: list[str] = Field(min_length=1)
    metrics: list[MetricName] = Field(min_length=1)
    limitations: list[str] = Field(min_length=1)
    maintainers: list[PackMaintainer] = Field(min_length=1)
    governance_owner: str
    digests: PackDigests
    includes: PackIncludes
    metadata: dict[str, Any] = Field(default_factory=dict)


class PackInspectReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_root: str
    manifest: BenchmarkPackManifest
    member_count: int
    public_digest: str
    missing_optional: list[str] = Field(default_factory=list)


def load_pack_manifest(path: Path) -> BenchmarkPackManifest:
    """Load and validate a pack.yaml (or JSON) document."""
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("pack manifest must be a mapping")
    return BenchmarkPackManifest.model_validate(data)


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _iter_pack_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = _normalize_rel(str(path.relative_to(root)))
        if rel == "pack.yaml":
            continue
        if any(part.startswith(".") for part in Path(rel).parts):
            continue
        files.append(path)
    # Sort by POSIX-normalized relative path so digests match across OSes.
    files.sort(key=lambda p: _normalize_rel(str(p.relative_to(root))))
    return files


def compute_pack_tree_digest(root: Path) -> str:
    """Digest of sorted public members (excluding pack.yaml digests self-ref)."""
    parts: list[dict[str, str]] = []
    for path in _iter_pack_files(root):
        rel = _normalize_rel(str(path.relative_to(root)))
        parts.append({"path": rel, "sha256": compute_file_digest(path)})
    return canonical_hash(parts)


def _normalize_text_newlines(data: bytes) -> bytes:
    """Collapse CRLF/CR to LF so digests are stable under ``core.autocrlf``."""
    if b"\0" in data:
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def compute_file_digest(path: Path) -> str:
    return sha256_hex(_normalize_text_newlines(Path(path).read_bytes()))


def resolve_pack_schema_path() -> Path | None:
    """Locate checked-in ``schemas/benchmark-pack-1.json`` when present."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[3] / "schemas" / "benchmark-pack-1.json",
        Path.cwd() / "schemas" / "benchmark-pack-1.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def lint_benchmark_pack(root: Path) -> DiagnosticReport:
    """Structural + schema lint for a benchmark pack directory."""
    root = Path(root).resolve()
    diagnostics = []

    if not root.is_dir():
        diagnostics.append(
            make_diagnostic(
                "EAC8001",
                path="pack.yaml",
                subject=str(root),
                summary=f"Not a benchmark pack directory: missing `{root}`",
            )
        )
        return DiagnosticReport(diagnostics=diagnostics)

    for name in sorted(REQUIRED_ROOT_FILES):
        if not (root / name).is_file():
            diagnostics.append(
                make_diagnostic(
                    "EAC8001",
                    path=name,
                    subject=str(root / name),
                    summary=f"Not an EnvAssure workspace: missing `{name}`",
                )
            )

    for dirname in sorted(REQUIRED_DIRS):
        if not (root / dirname).is_dir():
            diagnostics.append(
                make_diagnostic(
                    "EAC8001",
                    path=dirname,
                    subject=str(root / dirname),
                    summary=f"Not an EnvAssure workspace: missing `{dirname}/`",
                )
            )

    manifest_path = root / "pack.yaml"
    manifest: BenchmarkPackManifest | None = None
    if manifest_path.is_file():
        try:
            manifest = load_pack_manifest(manifest_path)
        except (ValidationError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            diagnostics.append(
                make_diagnostic(
                    "EAC8003",
                    reason=str(exc),
                    subject=str(manifest_path),
                    affected_artifacts=[str(manifest_path)],
                )
            )
    else:
        return DiagnosticReport(diagnostics=diagnostics)

    if manifest is not None:
        if manifest.pack_id != root.name and root.name not in {
            manifest.pack_id,
            manifest.pack_id.replace("_", "-"),
        }:
            diagnostics.append(
                make_diagnostic(
                    "EAC8003",
                    reason=(
                        f"pack_id {manifest.pack_id!r} does not match directory name {root.name!r}"
                    ),
                    subject=manifest.pack_id,
                )
            )

        for key in INCLUDE_KEYS:
            rel = _normalize_rel(getattr(manifest.includes, key))
            target = root / rel
            if not target.is_file():
                diagnostics.append(
                    make_diagnostic(
                        "EAC8001",
                        path=rel,
                        subject=rel,
                        summary=f"Not an EnvAssure workspace: missing `{rel}`",
                    )
                )

        schema_copy = root / "schemas" / "benchmark-pack-1.json"
        if schema_copy.is_dir() and not any(schema_copy.iterdir()):
            diagnostics.append(
                make_diagnostic(
                    "EAC8003",
                    reason="schemas/ directory is empty",
                    subject=str(schema_copy),
                )
            )

    return DiagnosticReport(diagnostics=diagnostics)


def verify_benchmark_pack(root: Path, *, check_secrets: bool = True) -> DiagnosticReport:
    """Lint plus digest and secret checks."""
    root = Path(root).resolve()
    report = lint_benchmark_pack(root)
    if report.has_errors():
        return report

    diagnostics = list(report.diagnostics)
    try:
        manifest = load_pack_manifest(root / "pack.yaml")
    except (ValidationError, ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
        diagnostics.append(
            make_diagnostic(
                "EAC8006",
                reason=f"cannot load pack.yaml: {exc}",
                subject=str(root),
            )
        )
        return DiagnosticReport(diagnostics=diagnostics)

    baseline_rel = _normalize_rel(manifest.includes.baseline)
    baseline_path = root / baseline_rel
    if baseline_path.is_file():
        try:
            world_data = json.loads(baseline_path.read_text(encoding="utf-8"))
            WorldDefinition.model_validate(world_data)
        except (ValidationError, json.JSONDecodeError, OSError) as exc:
            diagnostics.append(
                make_diagnostic(
                    "EAC8006",
                    reason=f"baseline world invalid: {exc}",
                    subject=baseline_rel,
                    affected_artifacts=[baseline_rel],
                )
            )
        else:
            actual = compute_file_digest(baseline_path)
            if manifest.digests.baseline_world and manifest.digests.baseline_world != actual:
                diagnostics.append(
                    make_diagnostic(
                        "EAC8006",
                        reason=(
                            f"baseline_world digest mismatch: declared "
                            f"{manifest.digests.baseline_world}, actual {actual}"
                        ),
                        subject=baseline_rel,
                    )
                )

    if manifest.digests.pack_tree:
        actual_tree = compute_pack_tree_digest(root)
        if actual_tree != manifest.digests.pack_tree:
            diagnostics.append(
                make_diagnostic(
                    "EAC8006",
                    reason=(
                        f"pack_tree digest mismatch: declared "
                        f"{manifest.digests.pack_tree}, actual {actual_tree}"
                    ),
                    subject=manifest.pack_id,
                )
            )

    if len(manifest.digests.hidden_oracle) != 64:
        diagnostics.append(
            make_diagnostic(
                "EAC8006",
                reason="hidden_oracle digest must be 64 hex chars",
                subject=manifest.pack_id,
            )
        )

    if check_secrets:
        for pattern_name, path in scan_path_for_secrets(root):
            diagnostics.append(
                make_diagnostic(
                    "EAC8006",
                    reason=f"secret-like pattern {pattern_name!r} in {path}",
                    subject=path,
                    affected_artifacts=[path],
                )
            )

    return DiagnosticReport(diagnostics=diagnostics)


def inspect_benchmark_pack(root: Path) -> PackInspectReport:
    """Return a structured inspect payload (raises if lint fails closed)."""
    root = Path(root).resolve()
    report = lint_benchmark_pack(root)
    if report.has_errors():
        raise ValueError(
            "; ".join(d.summary for d in report.diagnostics) or "benchmark pack lint failed"
        )
    manifest = load_pack_manifest(root / "pack.yaml")
    members = _iter_pack_files(root)
    return PackInspectReport(
        pack_root=str(root),
        manifest=manifest,
        member_count=len(members) + 1,  # include pack.yaml
        public_digest=compute_pack_tree_digest(root),
    )


def reproduce_benchmark_pack(
    root: Path,
    *,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Verify the pack and emit a small reproduce receipt.

    Full episode materialization for concealed workflows is delegated to
    ``eac benchmark`` when a ``workflow_id`` is present; this command always
    fail-closes on pack contract failures first.
    """
    root = Path(root).resolve()
    report = verify_benchmark_pack(root)
    if report.has_errors():
        raise ValueError(
            "; ".join(d.summary for d in report.diagnostics) or "benchmark pack verify failed"
        )
    manifest = load_pack_manifest(root / "pack.yaml")
    receipt: dict[str, Any] = {
        "ok": True,
        "pack_id": manifest.pack_id,
        "version": manifest.version,
        "workflow_id": manifest.workflow_id,
        "hidden_oracle_digest": manifest.digests.hidden_oracle,
        "public_digest": compute_pack_tree_digest(root),
        "connector_type": manifest.connector_type,
        "metrics": list(manifest.metrics),
        "note": (
            "Pack contract verified. Run `eac benchmark --concealed` (or the "
            "mapped workflow fixture) for episode-level reproduction."
        ),
    }
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / f"{manifest.pack_id}-reproduce.json"
        out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        receipt["receipt_path"] = str(out)
    return receipt


def discover_benchmark_packs(parent: Path) -> list[Path]:
    """Find child directories that contain pack.yaml."""
    parent = Path(parent)
    if not parent.is_dir():
        return []
    found: list[Path] = []
    for child in sorted(parent.iterdir()):
        if child.is_dir() and (child / "pack.yaml").is_file():
            found.append(child)
    return found


def summarize_pack_paths(paths: Iterable[Path]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for path in paths:
        try:
            manifest = load_pack_manifest(path / "pack.yaml")
            rows.append(
                {
                    "path": str(path),
                    "pack_id": manifest.pack_id,
                    "version": manifest.version,
                    "workflow_id": manifest.workflow_id,
                }
            )
        except (ValidationError, ValueError, OSError, yaml.YAMLError, json.JSONDecodeError) as exc:
            rows.append({"path": str(path), "error": str(exc)})
    return rows
