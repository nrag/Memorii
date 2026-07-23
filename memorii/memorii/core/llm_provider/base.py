from __future__ import annotations

from typing import Protocol

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse


class LLMProviderError(RuntimeError):
    """Expected transport, authentication, timeout, or provider-service failure."""


class LLMStructuredClient(Protocol):
    provider_name: str

    def complete_structured(
        self,
        request: LLMStructuredRequest,
        *,
        config: LLMRuntimeConfig,
    ) -> LLMStructuredResponse:
        ...
