from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest
from memorii.core.llm_provider.openai_provider import OpenAIStructuredClient, _build_structured_request_kwargs
from memorii.core.prompts.models import PromptModelDefaults


def _request() -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id="r1",
        prompt_ref="x:v1",
        prompt_hash="h",
        system="sys",
        user="usr",
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        model_defaults=PromptModelDefaults(provider="openai", model=None, timeout_seconds=5),
    )


def test_sdk_missing_raises_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(RuntimeError, match="Install the openai extra"):
        OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai", api_key=None))


def test_missing_key_raises_safe() -> None:
    with pytest.raises(RuntimeError, match="required"):
        OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai"))


def test_fake_sdk_response_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text='{"ok": true}', usage={"total_tokens": 12}, refusal=None)

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_Client))
    resp = OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai", api_key="x"))
    assert resp.provider == "openai"
    assert resp.raw_text == '{"ok": true}'
    assert resp.usage["total_tokens"] == 12
    assert resp.latency_ms is not None
    assert captured["text"]["format"]["schema"]["type"] == "object"
    assert captured["client_kwargs"]["max_retries"] == 2


def test_structured_request_kwargs_shape() -> None:
    kwargs = _build_structured_request_kwargs(request=_request(), model="gpt-4.1-mini")
    assert kwargs["model"] == "gpt-4.1-mini"
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True


def test_refusal_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Responses:
        def create(self, **kwargs):
            return SimpleNamespace(output=[], usage=None, refusal="policy")

    class _Client:
        def __init__(self, **kwargs):
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_Client))
    resp = OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai", api_key="x"))
    assert resp.refusal == "policy"


def test_api_key_not_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "not-a-real-key"

    class _Responses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="{}", usage=None, refusal=None)

    class _Client:
        def __init__(self, **kwargs):
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=_Client))
    resp = OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai", api_key=secret))
    assert secret not in str(resp.model_dump())
