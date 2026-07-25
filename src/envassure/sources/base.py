"""Source adapter protocol and shared helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from envassure.facts.models import SemanticFact


@runtime_checkable
class SourceAdapter(Protocol):
    """Parse a source artifact into candidate SemanticFact records."""

    kind: str

    def parse(self, path: Path) -> list[SemanticFact]:
        """Parse ``path`` and return candidate facts. Fail closed on bad input."""
        ...


class SourceParseError(ValueError):
    """Raised when a source adapter cannot parse an artifact."""

    def __init__(self, path: Path | str, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"Failed to parse source {self.path}: {reason}")
