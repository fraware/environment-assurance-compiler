"""In-memory SemanticFact store with JSON persistence."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from envassure.facts.models import FactStatus, SemanticFact


class FactStoreDocument(BaseModel):
    """On-disk envelope for a fact store snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    facts: list[SemanticFact] = Field(default_factory=list)


class FactStore:
    """Mutable store keyed by fact_id."""

    def __init__(self, facts: Iterable[SemanticFact] | None = None) -> None:
        self._facts: dict[str, SemanticFact] = {}
        if facts is not None:
            for fact in facts:
                self.add(fact)

    def add(self, fact: SemanticFact, *, overwrite: bool = False) -> None:
        if not overwrite and fact.fact_id in self._facts:
            raise ValueError(f"fact already exists: {fact.fact_id}")
        self._facts[fact.fact_id] = fact

    def get(self, fact_id: str) -> SemanticFact | None:
        return self._facts.get(fact_id)

    def list(
        self,
        *,
        status: FactStatus | None = None,
        subject_id: str | None = None,
        predicate: str | None = None,
    ) -> list[SemanticFact]:
        result: list[SemanticFact] = []
        for fact in self._facts.values():
            if status is not None and fact.status != status:
                continue
            if subject_id is not None and fact.subject.id != subject_id:
                continue
            if predicate is not None and fact.predicate != predicate:
                continue
            result.append(fact)
        return sorted(result, key=lambda f: f.fact_id)

    def __len__(self) -> int:
        return len(self._facts)

    def extend(self, facts: Iterable[SemanticFact], *, overwrite: bool = False) -> None:
        for fact in facts:
            self.add(fact, overwrite=overwrite)

    def save(self, path: Path, *, indent: int = 2) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = FactStoreDocument(facts=self.list())
        path.write_text(
            json.dumps(doc.model_dump(mode="json"), indent=indent) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> FactStore:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            facts = [SemanticFact.model_validate(item) for item in raw]
            return cls(facts)
        doc = FactStoreDocument.model_validate(raw)
        return cls(doc.facts)
