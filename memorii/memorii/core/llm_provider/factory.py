from __future__ import annotations

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMStructuredClient
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.noop import NoopLLMStructuredClient
from memorii.core.llm_provider.openai_provider import OpenAIStructuredClient


class LLMClientFactory:
    @staticmethod
    def from_config(config: LLMRuntimeConfig) -> LLMStructuredClient:
        provider = config.provider.strip().lower()
        if provider == "none":
            return NoopLLMStructuredClient()
        if provider == "fake":
            return FakeLLMStructuredClient(default_response="{}")
        if provider == "openai":
            return OpenAIStructuredClient()
        raise ValueError(f"Unsupported LLM provider: {provider}")
