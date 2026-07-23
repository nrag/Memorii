from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest
from memorii.core.llm_provider.openai_provider import OpenAIStructuredClient, _build_structured_request_kwargs
from memorii.core.prompts.models import PromptModelDefaults


class _FakeOpenAIError(Exception):
    pass


def _fake_openai_module(client_type: type[object]) -> SimpleNamespace:
    return SimpleNamespace(OpenAI=client_type, OpenAIError=_FakeOpenAIError)


def _request() -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id="r1",
        prompt_ref="x:v1",
        prompt_hash="h",
        system="sys",
        user="usr",
        output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False},
        model_defaults=PromptModelDefaults(
            provider="openai",
            model=None,
            temperature=0.2,
            max_tokens=321,
            timeout_seconds=5,
        ),
    )


def test_sdk_missing_raises_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "openai", None)
    with pytest.raises(RuntimeError, match="Install the local, live, or prod extra"):
        OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai", api_key=None))


def test_missing_key_raises_safe() -> None:
    with pytest.raises(RuntimeError, match="required"):
        OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai"))


def test_fake_sdk_response_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                id="resp_provider_1",
                model="gpt-4.1-mini-2026-06-01",
                status="completed",
                output_text='{"ok": true}',
                usage={"total_tokens": 12},
                refusal=None,
            )

    class _Client:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", _fake_openai_module(_Client))
    resp = OpenAIStructuredClient().complete_structured(
        _request(),
        config=LLMRuntimeConfig(provider="openai", api_key="x", max_retries=0),
    )
    assert resp.provider == "openai"
    assert resp.raw_text == '{"ok": true}'
    assert resp.usage["total_tokens"] == 12
    assert resp.latency_ms is not None
    assert resp.requested_model == "gpt-4.1-mini"
    assert resp.actual_model == "gpt-4.1-mini-2026-06-01"
    assert resp.provider_request_id == "resp_provider_1"
    assert resp.response_status == "completed"
    assert resp.effective_settings == {
        "model": "gpt-4.1-mini",
        "temperature": 0.2,
        "max_output_tokens": 321,
        "timeout_seconds": 5.0,
    }
    assert resp.attempt_count == 1
    assert resp.sdk_max_retries == 0
    assert captured["text"]["format"]["schema"]["type"] == "object"
    assert captured["temperature"] == 0.2
    assert captured["max_output_tokens"] == 321
    assert captured["client_kwargs"]["max_retries"] == 0


def test_sdk_retry_budget_does_not_claim_an_unobservable_attempt_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Responses:
        def create(self, **kwargs):
            return SimpleNamespace(
                output_text='{"ok": true}',
                usage=None,
                refusal=None,
            )

    class _Client:
        def __init__(self, **kwargs):
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", _fake_openai_module(_Client))
    response = OpenAIStructuredClient().complete_structured(
        _request(),
        config=LLMRuntimeConfig(provider="openai", api_key="x", max_retries=2),
    )

    assert response.actual_model is None
    assert response.attempt_count is None
    assert response.sdk_max_retries == 2
    assert response.finish_reason is None


def test_structured_request_kwargs_shape() -> None:
    kwargs = _build_structured_request_kwargs(request=_request(), model="gpt-4.1-mini")
    assert kwargs["model"] == "gpt-4.1-mini"
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["text"]["format"]["strict"] is True
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_output_tokens"] == 321


def test_refusal_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Responses:
        def create(self, **kwargs):
            return SimpleNamespace(output=[], usage=None, refusal="policy")

    class _Client:
        def __init__(self, **kwargs):
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", _fake_openai_module(_Client))
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

    monkeypatch.setitem(sys.modules, "openai", _fake_openai_module(_Client))
    resp = OpenAIStructuredClient().complete_structured(_request(), config=LLMRuntimeConfig(provider="openai", api_key=secret))
    assert secret not in str(resp.model_dump())


def test_sdk_provider_error_is_wrapped_without_payload_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Responses:
        def create(self, **kwargs):
            del kwargs
            raise _FakeOpenAIError("sensitive upstream payload")

    class _Client:
        def __init__(self, **kwargs):
            del kwargs
            self.responses = _Responses()

    monkeypatch.setitem(sys.modules, "openai", _fake_openai_module(_Client))

    with pytest.raises(RuntimeError, match="OpenAI request failed: _FakeOpenAIError") as exc_info:
        OpenAIStructuredClient().complete_structured(
            _request(),
            config=LLMRuntimeConfig(provider="openai", api_key="x"),
        )

    assert "sensitive upstream payload" not in str(exc_info.value)


def test_sdk_constructor_error_is_wrapped_without_payload_leakage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Client:
        def __init__(self, **kwargs):
            del kwargs
            raise _FakeOpenAIError("sensitive constructor payload")

    monkeypatch.setitem(sys.modules, "openai", _fake_openai_module(_Client))

    with pytest.raises(RuntimeError, match="OpenAI request failed: _FakeOpenAIError") as exc_info:
        OpenAIStructuredClient().complete_structured(
            _request(),
            config=LLMRuntimeConfig(provider="openai", api_key="x"),
        )

    assert "sensitive constructor payload" not in str(exc_info.value)
