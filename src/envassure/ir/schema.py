"""JSON Schema export for IR (Draft 2020-12)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from envassure.ir.models import WorldDefinition
from envassure.ir.primitives import IR_PRIOR_STABLE, IR_VERSION, SUPPORTED_READ_VERSIONS


def world_json_schema() -> dict[str, Any]:
    """JSON Schema for the compiler's write-current IR version."""
    schema = WorldDefinition.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://envassure.dev/schemas/world-{IR_VERSION}.json"
    schema["title"] = "WorldDefinition"
    schema["x-envassure-ir-version"] = IR_VERSION
    schema["x-envassure-supported-read-versions"] = sorted(SUPPORTED_READ_VERSIONS)
    schema["x-envassure-prior-stable"] = IR_PRIOR_STABLE
    return schema


def export_schemas(directory: Path) -> list[Path]:
    """Write ``world-{IR_VERSION}.json`` and alias ``world.json``.

    Prior-stable schemas (e.g. ``world-0.1.0.json``) are frozen historical
    artifacts and are not overwritten by this export.
    """
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    world_path = directory / f"world-{IR_VERSION}.json"
    world_path.write_text(json.dumps(world_json_schema(), indent=2) + "\n", encoding="utf-8")
    written.append(world_path)
    latest = directory / "world.json"
    latest.write_text(world_path.read_text(encoding="utf-8"), encoding="utf-8")
    written.append(latest)
    return written
