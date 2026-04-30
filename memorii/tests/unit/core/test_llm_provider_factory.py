from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.factory import LLMClientFactory
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.noop import NoopLLMStructuredClient
from memorii.core.llm_provider.openai_provider import OpenAIStructuredClient


def test_provider_none_returns_noop() -> None:
    client = LLMClientFactory.from_config(LLMRuntimeConfig(provider="none"))
    assert isinstance(client, NoopLLMStructuredClient)


def test_provider_fake_returns_fake() -> None:
    client = LLMClientFactory.from_config(LLMRuntimeConfig(provider="fake"))
    assert isinstance(client, FakeLLMStructuredClient)


def test_provider_openai_returns_openai_client_without_api_key() -> None:
    client = LLMClientFactory.from_config(LLMRuntimeConfig(provider="openai"))
    assert isinstance(client, OpenAIStructuredClient)


def test_unsupported_provider_raises() -> None:
    try:
        LLMClientFactory.from_config(LLMRuntimeConfig(provider="bogus"))
    except ValueError as exc:
        assert "Unsupported LLM provider" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
