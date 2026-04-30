from __future__ import annotations

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse


class FakeLLMStructuredClient:
    def __init__(
        self,
        *,
        provider_name: str = "fake",
        responses_by_request_id: dict[str, str] | None = None,
        default_response: str | None = None,
        raise_on_request: bool = False,
    ) -> None:
        self.provider_name = provider_name
        self._responses_by_request_id = responses_by_request_id or {}
        self._default_response = default_response
        self._raise_on_request = raise_on_request
        self.last_request: LLMStructuredRequest | None = None

    def complete_structured(
        self,
        request: LLMStructuredRequest,
        *,
        config: LLMRuntimeConfig,
    ) -> LLMStructuredResponse:
        del config
        self.last_request = request
        if self._raise_on_request:
            raise RuntimeError("fake provider configured to fail")

        raw_text = self._responses_by_request_id.get(request.request_id, self._default_response or "{}")
        return LLMStructuredResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=request.model_defaults.model,
            raw_text=raw_text,
            valid_json=False,
            schema_valid=False,
        )
