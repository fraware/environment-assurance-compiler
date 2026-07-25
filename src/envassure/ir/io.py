"""IR load/save helpers."""

from __future__ import annotations

import json
from pathlib import Path

from envassure.ir.models import WorldDefinition


def load_world(path: Path) -> WorldDefinition:
    data = json.loads(path.read_text(encoding="utf-8"))
    return WorldDefinition.model_validate(data)


def save_world(path: Path, world: WorldDefinition, *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(world.model_dump(mode="json"), indent=indent) + "\n",
        encoding="utf-8",
    )
