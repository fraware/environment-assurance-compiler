"""Environment Assurance Compiler (`envassure`)."""

from __future__ import annotations

# Defined before heavier imports so runtime/engine can read the version without
# circular-import failures during package initialization.
__version__ = "0.1.0a0"

from envassure.api import World, action, actor, state, task

__all__ = [
    "World",
    "__version__",
    "action",
    "actor",
    "state",
    "task",
]
