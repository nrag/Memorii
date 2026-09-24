"""OpenAI Responses binding for the project-assertions semantic profile."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from memorii.core.semantic_ingestion.contracts import (
    BootstrapSemanticProposalRequestV3,
    ProviderSemanticProposal,
)
from memorii.core.semantic_ingestion.project_assertions import (
    PROJECT_ASSERTIONS_OUTPUT_SCHEMA,
    PROJECT_ASSERTIONS_PROMPT,
    ProjectAssertionProviderProposalAdapter,
)

OPENAI_PROJECT_ASSERTIONS_MODEL = "gpt-4.1-nano"


class OpenAIResponsesClient(Protocol):
    """Narrow provider boundary with no graph or source-store access."""

    def complete(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        source_segment: str,
        output_schema: dict[str, object],
        store: bool,
        background: bool,
    ) -> str | None: ...


class OpenAIResponsesApiClient:
    """Direct Responses API client with fixed request limits."""

    def complete(self, **kwargs: Any) -> str | None:
        try:
            from openai import OpenAI, OpenAIError
        except ImportError:
            return None
        api_key = kwargs["api_key"]
        try:
            response = OpenAI(api_key=api_key, timeout=10.0, max_retries=0).responses.create(
                model=kwargs["model"],
                input=[
                    {"role": "system", "content": [{"type": "input_text", "text": kwargs["system_prompt"]}]},
                    {"role": "user", "content": [{"type": "input_text", "text": kwargs["source_segment"]}]},
                ],
                text={"format": {"type": "json_schema", "name": "memorii_project_assertions", "strict": True, "schema": kwargs["output_schema"]}},
                store=kwargs["store"], background=kwargs["background"],
            )
        except OpenAIError:
            return None
        value = getattr(response, "output_text", None)
        return value if isinstance(value, str) else None


class BootstrapV3OpenAIProjectAssertionsTransport:
    """The V3 transport; egress authority is checked before credentials or I/O."""

    def __init__(
        self,
        *,
        adapter: ProjectAssertionProviderProposalAdapter,
        egress_authorized: Callable[[BootstrapSemanticProposalRequestV3], bool],
        credential_resolver: Callable[[], str | None],
        client: OpenAIResponsesClient | None = None,
    ) -> None:
        self._adapter = adapter
        self._egress_authorized = egress_authorized
        self._credential_resolver = credential_resolver
        self._client = client or OpenAIResponsesApiClient()

    def __call__(self, request: BootstrapSemanticProposalRequestV3) -> tuple[ProviderSemanticProposal, bytes] | None:
        if request.provider_egress_decision_digest is None or not self._egress_authorized(request):
            return None
        api_key = self._credential_resolver()
        if not api_key:
            return None
        response = self._client.complete(
            api_key=api_key, model=OPENAI_PROJECT_ASSERTIONS_MODEL,
            system_prompt=PROJECT_ASSERTIONS_PROMPT,
            source_segment=request.segment.segment_text,
            output_schema=PROJECT_ASSERTIONS_OUTPUT_SCHEMA,
            store=False, background=False,
        )
        # Revalidate after remote egress so authority revoked while the request
        # was in flight cannot reach normalization or graph publication.
        if response is None or not self._egress_authorized(request):
            return None
        proposal = self._adapter.from_response(request=request, response_text=response)
        if proposal is None or not self._egress_authorized(request):
            return None
        return proposal, response.encode("utf-8")


__all__ = [
    "BootstrapV3OpenAIProjectAssertionsTransport", "OPENAI_PROJECT_ASSERTIONS_MODEL",
    "OpenAIResponsesApiClient", "OpenAIResponsesClient",
]
