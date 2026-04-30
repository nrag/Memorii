from __future__ import annotations

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse


class NoopLLMStructuredClient:
    provider_name = "none"

    def complete_structured(self, request: LLMStructuredRequest, *, config: LLMRuntimeConfig) -> LLMStructuredResponse:
        del config
        return LLMStructuredResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            raw_text="",
            valid_json=False,
            schema_valid=False,
            error="No LLM provider configured.",
        )
