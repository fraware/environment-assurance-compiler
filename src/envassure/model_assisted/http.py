"""Optional HTTP proposal provider (requires ``[model-assisted]``).

Disabled unless constructed with ``enabled=True`` and a ``base_url``.
Default CI never performs network calls; use :class:`StubProposalProvider`
for offline tests.
"""

from __future__ import annotations

import json
from typing import Any

from envassure.model_assisted import ModelProposal, propose
from envassure.model_assisted.providers import require_model_assisted_extra


def _digest(payload: str) -> str:
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class HttpProposalProvider:
    """Non-authoritative HTTP provider behind the model-assisted extra.

    Fail-closed unless ``enabled=True``. Still never elevates authority —
    responses are wrapped as tainted ``model_proposal`` artifacts with digests.
    """

    def __init__(
        self,
        *,
        base_url: str,
        enabled: bool = False,
        model_id: str = "http-provider",
        api_key: str | None = None,
        timeout_s: float = 30.0,
        path: str = "/v1/proposals",
    ) -> None:
        require_model_assisted_extra()
        if not enabled:
            raise PermissionError(
                "HttpProposalProvider is disabled; pass enabled=True only for "
                "explicit opt-in runs (never required in CI)"
            )
        if not base_url.strip():
            raise ValueError("HttpProposalProvider requires a non-empty base_url")
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._path = path if path.startswith("/") else f"/{path}"
        self._enabled = enabled

    @property
    def model_id(self) -> str:
        return self._model_id

    def complete(
        self,
        prompt: str,
        *,
        subject: str,
        predicate: str,
        value: Any = None,
        source_context: str | dict[str, Any] | None = None,
        untrusted_excerpts: list[str] | None = None,
    ) -> ModelProposal:
        httpx = require_model_assisted_extra()
        prompt_digest = _digest(prompt)
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        body = {
            "prompt": prompt,
            "prompt_digest": prompt_digest,
            "subject": subject,
            "predicate": predicate,
            "value": value,
            "model_id": self._model_id,
        }
        url = f"{self._base_url}{self._path}"
        with httpx.Client(timeout=self._timeout_s) as client:
            response = client.post(url, headers=headers, content=json.dumps(body, default=str))
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise ValueError("HTTP proposal provider returned a non-object JSON body")
        resolved_subject = str(data.get("subject") or subject)
        resolved_predicate = str(data.get("predicate") or predicate)
        resolved_value = data.get("value", value)
        proposal = propose(
            summary=str(data.get("summary") or f"http response for {resolved_subject}"),
            subject=resolved_subject,
            predicate=resolved_predicate,
            value=resolved_value if resolved_value is not None else {"http": True},
            model_id=str(data.get("model_id") or self._model_id),
            prompt_digest=prompt_digest,
            source_context=source_context,
            untrusted_excerpts=untrusted_excerpts,
            raw_excerpt=str(data.get("raw_excerpt") or "")[:2000] or None,
        )
        proposal.isolation = {
            **proposal.isolation,
            "taint": "model_proposal",
            "isolated_from_source_facts": True,
            "provider": "http",
            "base_url_host": self._base_url,
        }
        proposal.metadata = {
            **proposal.metadata,
            "provider": "http",
            "auto_accept": False,
            "http_status": response.status_code,
        }
        return proposal
