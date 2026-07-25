"""Proposal provider protocol, registry, and extra gate helpers."""

from __future__ import annotations

import importlib.metadata
from typing import Any, Protocol, runtime_checkable

PROPOSAL_PROVIDER_ENTRY_GROUP = "envassure.proposal_providers"

MODEL_ASSISTED_IMPORT_ERROR = (
    "httpx is required for non-stub model-assisted providers. "
    "Install with: pip install 'envassure[model-assisted]'"
)


def require_model_assisted_extra() -> Any:
    """Import ``httpx`` or raise a fail-closed ``ImportError``."""
    try:
        import httpx
    except ImportError as exc:
        raise ImportError(MODEL_ASSISTED_IMPORT_ERROR) from exc
    return httpx


@runtime_checkable
class ProposalProvider(Protocol):
    """Protocol for offline or opt-in HTTP proposal providers."""

    @property
    def model_id(self) -> str:
        """Provider model identifier recorded on proposals."""

    def complete(
        self,
        prompt: str,
        *,
        subject: str,
        predicate: str,
        value: Any = None,
        source_context: str | dict[str, Any] | None = None,
        untrusted_excerpts: list[str] | None = None,
    ) -> Any:
        """Return a non-authoritative proposal for *prompt*."""


def get_provider(
    name: str = "stub",
    **kwargs: Any,
) -> ProposalProvider:
    """Resolve a proposal provider by name.

    * ``stub`` / ``offline`` — always available (core).
    * ``http`` / ``httpx`` — requires ``[model-assisted]`` and explicit enable.

    Unknown names consult the ``envassure.proposal_providers`` entry-point group.
    """
    key = name.strip().lower()
    if key in {"stub", "offline"}:
        from envassure.model_assisted import StubProposalProvider

        return StubProposalProvider(**kwargs)
    if key in {"http", "httpx"}:
        require_model_assisted_extra()
        from envassure.model_assisted.http import HttpProposalProvider

        return HttpProposalProvider(**kwargs)
    loaded = _load_entry_point_provider(key, **kwargs)
    if loaded is not None:
        return loaded
    raise KeyError(
        f"unknown proposal provider {name!r}; "
        "use 'stub' or install 'envassure[model-assisted]' for 'http'"
    )


def _load_entry_point_provider(name: str, **kwargs: Any) -> ProposalProvider | None:
    eps = importlib.metadata.entry_points(group=PROPOSAL_PROVIDER_ENTRY_GROUP)
    for ep in eps:
        if ep.name != name:
            continue
        target = ep.load()
        instance: Any = target(**kwargs) if isinstance(target, type) or callable(target) else None
        if instance is None:
            continue
        return instance  # type: ignore[no-any-return]
    return None


def list_provider_entry_points() -> list[str]:
    """Return registered proposal provider entry-point names."""
    eps = importlib.metadata.entry_points(group=PROPOSAL_PROVIDER_ENTRY_GROUP)
    return sorted({ep.name for ep in eps})
