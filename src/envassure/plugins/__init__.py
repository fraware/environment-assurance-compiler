"""Plugin discovery, allowlists, templates, and packaging helpers."""

from __future__ import annotations

import importlib.metadata
import json
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.diagnostics.factory import make_diagnostic
from envassure.diagnostics.models import DiagnosticReport

PLUGIN_API_VERSION = "0.1.0"
ENTRY_POINT_GROUP = "envassure.plugins"

PluginKind = Literal["generic", "source_adapter", "codegen_target", "proposal_provider"]


class PluginSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    api_version: str = PLUGIN_API_VERSION
    kind: str = "generic"
    module: str | None = None
    entry_point: str | None = None
    digest: str | None = None
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class PluginAllowlist:
    """Release-mode allowlist of plugin names (optionally pinned versions)."""

    names: set[str] = field(default_factory=set)
    versions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, mapping: dict[str, str]) -> PluginAllowlist:
        return cls(names=set(mapping), versions=dict(mapping))

    @classmethod
    def from_names(cls, names: set[str] | list[str]) -> PluginAllowlist:
        return cls(names=set(names))

    def allows(self, name: str, version: str | None = None) -> bool:
        if name not in self.names:
            return False
        if name not in self.versions:
            return True
        permitted = self.versions[name]
        if permitted == "*":
            return True
        if version is None:
            return True
        return permitted == version


def discover_plugins() -> list[PluginSpec]:
    specs: list[PluginSpec] = []
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover — older importlib
        eps = importlib.metadata.entry_points().get(ENTRY_POINT_GROUP, [])  # type: ignore[assignment]
    for ep in eps:
        version = "0"
        dist = getattr(ep, "dist", None)
        if dist is not None and getattr(dist, "version", None):
            version = str(dist.version)
        specs.append(
            PluginSpec(
                name=ep.name,
                version=version,
                module=ep.value,
                entry_point=ep.value,
                kind="entry_point",
            )
        )
    return specs


def check_allowlist(
    plugins: list[PluginSpec],
    allowlist: PluginAllowlist | set[str] | list[str] | dict[str, str],
    *,
    release_mode: bool = True,
) -> DiagnosticReport:
    report = DiagnosticReport()
    if not release_mode:
        return report
    if isinstance(allowlist, PluginAllowlist):
        allowed = allowlist
    elif isinstance(allowlist, dict):
        allowed = PluginAllowlist.from_mapping(allowlist)
    else:
        allowed = PluginAllowlist.from_names(allowlist)
    for plugin in plugins:
        if not allowed.allows(plugin.name, plugin.version):
            report.add(
                make_diagnostic(
                    "EAC9006",
                    reason=f"plugin {plugin.name!r} not in release allowlist",
                    subject=plugin.name,
                    details={"version": plugin.version},
                )
            )
    return report


def create_plugin_template(name: str, *, kind: PluginKind = "generic") -> str:
    """Return a single-module template string for the given plugin kind."""
    if kind == "source_adapter":
        return _source_adapter_template(name)
    if kind == "codegen_target":
        return _codegen_target_template(name)
    return _generic_template(name)


def create_plugin_scaffold(
    directory: Path,
    *,
    name: str,
    version: str = "0.1.0",
    kind: PluginKind = "generic",
) -> PluginSpec:
    """Create an offline-usable plugin package scaffold on disk."""
    directory.mkdir(parents=True, exist_ok=True)
    module_name = name.replace("-", "_")
    pkg = directory / module_name
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text(create_plugin_template(name, kind=kind), encoding="utf-8")

    capabilities = {
        "generic": ["scaffold"],
        "source_adapter": ["source_adapter", "parse"],
        "codegen_target": ["codegen_target", "generate"],
    }[kind]

    entry_attr = {
        "generic": "register",
        "source_adapter": "register",
        "codegen_target": "register",
    }[kind]

    spec = PluginSpec(
        name=name,
        version=version,
        kind=kind,
        entry_point=f"{module_name}:{entry_attr}",
        module=f"{module_name}:{entry_attr}",
        description=f"Scaffolded {kind} plugin {name}",
        capabilities=capabilities,
        metadata={"template": kind, "offline": True},
    )
    (directory / "plugin.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    (directory / "pyproject.toml").write_text(
        _pyproject_toml(name=name, module_name=module_name, version=version, kind=kind),
        encoding="utf-8",
    )
    (directory / "README.md").write_text(
        f"# {name}\n\nEnvAssure `{kind}` plugin scaffold (offline).\n\n"
        f"API version: {PLUGIN_API_VERSION}\n\n"
        "Commands:\n\n"
        "```text\neac plugins test .\neac plugins package . -o dist/plugin.zip\neac plugins doctor\n```\n",
        encoding="utf-8",
    )
    tests_dir = directory / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_plugin_smoke.py").write_text(
        _smoke_test(module_name=module_name, kind=kind),
        encoding="utf-8",
    )
    return spec


def validate_plugin(spec_or_dir: PluginSpec | Path) -> DiagnosticReport:
    """Offline plugin test: load spec, check API version, required files, and register()."""
    report = DiagnosticReport()
    directory: Path | None = None
    if isinstance(spec_or_dir, Path):
        directory = spec_or_dir if spec_or_dir.is_dir() else spec_or_dir.parent
        spec_path = directory / "plugin.json" if directory.is_dir() else spec_or_dir
        if not spec_path.is_file():
            report.add(
                make_diagnostic(
                    "EAC9006",
                    reason=f"missing plugin.json at {spec_path}",
                    subject=str(spec_or_dir),
                )
            )
            return report
        spec = PluginSpec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))
    else:
        spec = spec_or_dir

    if spec.api_version.split(".")[0] != PLUGIN_API_VERSION.split(".")[0]:
        report.add(
            make_diagnostic(
                "EAC9006",
                reason=(
                    f"plugin API version {spec.api_version!r} incompatible with "
                    f"compiler {PLUGIN_API_VERSION!r}"
                ),
                subject=spec.name,
            )
        )
    entry = spec.entry_point or spec.module
    if not entry or ":" not in entry:
        report.add(
            make_diagnostic(
                "EAC9006",
                reason="plugin entry_point must be module:attr",
                subject=spec.name,
            )
        )

    if directory is not None:
        required = ["plugin.json", "pyproject.toml"]
        module_name = (entry or "x:y").split(":", 1)[0]
        required.append(f"{module_name}/__init__.py")
        for rel in required:
            if not (directory / rel).is_file():
                report.add(
                    make_diagnostic(
                        "EAC9006",
                        reason=f"scaffold missing required file {rel}",
                        subject=spec.name,
                    )
                )
        # Execute register() offline by loading the local package path.
        if not report.has_errors():
            try:
                meta = _load_local_register(directory, entry)
                if not isinstance(meta, dict) or "name" not in meta:
                    report.add(
                        make_diagnostic(
                            "EAC9006",
                            reason="register() must return a dict with name",
                            subject=spec.name,
                        )
                    )
                elif meta.get("kind") is not None and meta.get("kind") != spec.kind:
                    report.add(
                        make_diagnostic(
                            "EAC9006",
                            reason=(
                                f"register kind {meta.get('kind')!r} "
                                f"!= plugin.json kind {spec.kind!r}"
                            ),
                            subject=spec.name,
                        )
                    )
                if spec.kind == "source_adapter":
                    _assert_local_attr(directory, module_name, "parse", report, spec.name)
                if spec.kind == "codegen_target":
                    _assert_local_attr(directory, module_name, "generate", report, spec.name)
            except Exception as exc:
                report.add(
                    make_diagnostic(
                        "EAC9006",
                        reason=f"failed to load plugin: {exc}",
                        subject=spec.name,
                    )
                )
    return report


def package_plugin(directory: Path, output: Path) -> Path:
    """Package plugin scaffold files into a zip for distribution."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix == ".pyc":
                continue
            zf.write(path, arcname=path.relative_to(directory).as_posix())
    return output


def doctor_plugins(
    *,
    allowlist: PluginAllowlist | set[str] | list[str] | None = None,
    release_mode: bool = False,
    path: Path | None = None,
) -> DiagnosticReport:
    report = DiagnosticReport()
    plugins = discover_plugins()
    if path is not None:
        local = validate_plugin(path)
        report.extend(local.diagnostics)
        if (path / "plugin.json").is_file() or path.name == "plugin.json":
            spec_path = path / "plugin.json" if path.is_dir() else path
            if spec_path.is_file():
                local_spec = PluginSpec.model_validate(
                    json.loads(spec_path.read_text(encoding="utf-8"))
                )
                plugins = [*plugins, local_spec]
    report.context = {
        "plugin_count": len(plugins),
        "plugins": [p.model_dump(mode="json") for p in plugins],
        "api_version": PLUGIN_API_VERSION,
    }
    if allowlist is not None:
        report.extend(check_allowlist(plugins, allowlist, release_mode=release_mode).diagnostics)
    return report


def load_plugin_callable(module_path: str, attr: str = "register") -> Callable[..., Any]:
    module_name, _, maybe_attr = module_path.partition(":")
    target_attr = maybe_attr or attr
    import importlib

    mod = importlib.import_module(module_name)
    fn = getattr(mod, target_attr)
    if not callable(fn):
        raise TypeError(f"{module_path} is not callable")
    return fn


def _generic_template(name: str) -> str:
    return f'''"""EnvAssure plugin: {name}."""

from __future__ import annotations

PLUGIN_NAME = "{name}"
PLUGIN_API_VERSION = "{PLUGIN_API_VERSION}"
PLUGIN_KIND = "generic"


def register() -> dict[str, str]:
    return {{
        "name": PLUGIN_NAME,
        "api_version": PLUGIN_API_VERSION,
        "kind": PLUGIN_KIND,
    }}
'''


def _source_adapter_template(name: str) -> str:
    return f'''"""EnvAssure source-adapter plugin: {name}."""

from __future__ import annotations

from pathlib import Path
from typing import Any

PLUGIN_NAME = "{name}"
PLUGIN_API_VERSION = "{PLUGIN_API_VERSION}"
PLUGIN_KIND = "source_adapter"


def register() -> dict[str, str]:
    return {{
        "name": PLUGIN_NAME,
        "api_version": PLUGIN_API_VERSION,
        "kind": PLUGIN_KIND,
        "adapter_kind": PLUGIN_NAME.replace("-", "_"),
    }}


def parse(path: Path) -> list[dict[str, Any]]:
    """Parse *path* into candidate fact dicts (offline scaffold).

    Production adapters should return ``SemanticFact`` models; this scaffold
    returns plain dicts so the plugin tests without importing host IR.
    """
    text = Path(path).read_text(encoding="utf-8")
    return [
        {{
            "subject_kind": "document",
            "subject_id": Path(path).stem,
            "predicate": "raw_text_present",
            "value": bool(text.strip()),
            "source_refs": [str(path)],
            "extraction_method": "plugin:{name}",
        }}
    ]
'''


def _codegen_target_template(name: str) -> str:
    return f'''"""EnvAssure codegen-target plugin: {name}."""

from __future__ import annotations

from typing import Any

PLUGIN_NAME = "{name}"
PLUGIN_API_VERSION = "{PLUGIN_API_VERSION}"
PLUGIN_KIND = "codegen_target"


def register() -> dict[str, str]:
    return {{
        "name": PLUGIN_NAME,
        "api_version": PLUGIN_API_VERSION,
        "kind": PLUGIN_KIND,
        "target": PLUGIN_NAME.replace("-", "_"),
    }}


def generate(world: dict[str, Any]) -> str:
    """Generate target source from a world IR dict (offline scaffold)."""
    env_id = world.get("environment_id", "unknown")
    actions = world.get("actions") or []
    lines = [
        f"# Generated by {name} for {{env_id}}",
        f"ENVIRONMENT_ID = {{env_id!r}}",
        f"ACTION_COUNT = {{len(actions)}}",
    ]
    return "\\n".join(lines) + "\\n"
'''


def _pyproject_toml(*, name: str, module_name: str, version: str, kind: str) -> str:
    return f'''[project]
name = "{name}"
version = "{version}"
description = "EnvAssure {kind} plugin"
requires-python = ">=3.11"
dependencies = []

[project.entry-points."envassure.plugins"]
{name} = "{module_name}:register"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{module_name}"]
'''


def _smoke_test(*, module_name: str, kind: str) -> str:
    extra = ""
    if kind == "source_adapter":
        extra = f"""
def test_parse(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("hello", encoding="utf-8")
    from {module_name} import parse
    facts = parse(sample)
    assert facts and facts[0]["predicate"] == "raw_text_present"
"""
    elif kind == "codegen_target":
        extra = f"""
def test_generate():
    from {module_name} import generate
    out = generate({{"environment_id": "demo", "actions": [{{"id": "a"}}]}})
    assert "demo" in out
"""
    return f'''"""Offline smoke test for scaffolded plugin."""

from {module_name} import register


def test_register():
    meta = register()
    assert meta["name"]
    assert meta["api_version"]
    assert meta["kind"] == "{kind}"
{extra}
'''


def _load_local_register(directory: Path, entry: str) -> dict[str, Any]:
    import importlib.util
    import sys

    module_name, _, attr = entry.partition(":")
    attr = attr or "register"
    init_path = directory / module_name / "__init__.py"
    if not init_path.is_file():
        raise FileNotFoundError(init_path)
    # Unique module name to avoid collisions across tests.
    mod_id = f"_eac_plugin_{module_name}_{abs(hash(str(directory))) & 0xFFFF}"
    spec = importlib.util.spec_from_file_location(mod_id, init_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {init_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_id] = mod
    spec.loader.exec_module(mod)
    fn = getattr(mod, attr)
    result = fn()
    if not isinstance(result, dict):
        raise TypeError("register() must return dict")
    return result


def _assert_local_attr(
    directory: Path,
    module_name: str,
    attr: str,
    report: DiagnosticReport,
    subject: str,
) -> None:
    import importlib.util
    import sys

    init_path = directory / module_name / "__init__.py"
    mod_id = f"_eac_plugin_check_{module_name}_{attr}"
    spec = importlib.util.spec_from_file_location(mod_id, init_path)
    if spec is None or spec.loader is None:
        report.add(
            make_diagnostic(
                "EAC9006",
                reason=f"cannot load module for attr {attr}",
                subject=subject,
            )
        )
        return
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_id] = mod
    spec.loader.exec_module(mod)
    if not hasattr(mod, attr) or not callable(getattr(mod, attr)):
        report.add(
            make_diagnostic(
                "EAC9006",
                reason=f"plugin missing required callable {attr}()",
                subject=subject,
            )
        )
