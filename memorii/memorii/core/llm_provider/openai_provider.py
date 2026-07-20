from __future__ import annotations

import time
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.base import LLMProviderError
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse


class OpenAIStructuredClient:
    provider_name = "openai"

    def complete_structured(self, request: LLMStructuredRequest, *, config: LLMRuntimeConfig) -> LLMStructuredResponse:
        try:
            from openai import OpenAI, OpenAIError
        except ImportError as exc:
            raise LLMProviderError(
                "OpenAI SDK is required for OpenAIStructuredClient. Install the local, live, or prod extra."
            ) from exc

        api_key = config.require_api_key().get_secret_value()
        model = request.model_defaults.model or config.model or "gpt-4.1-mini"
        timeout = request.model_defaults.timeout_seconds or config.timeout_seconds
        started = time.perf_counter()
        try:
            client = OpenAI(api_key=api_key, timeout=timeout, max_retries=config.max_retries)
            response = client.responses.create(**_build_structured_request_kwargs(request=request, model=model))
        except OpenAIError as exc:
            raise LLMProviderError(f"OpenAI request failed: {type(exc).__name__}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        return LLMStructuredResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            requested_model=model,
            actual_model=_string_attribute(response, "model"),
            provider_request_id=_string_attribute(response, "id"),
            response_status=_string_attribute(response, "status"),
            finish_reason=_extract_finish_reason(response),
            sdk_version=_openai_sdk_version(),
            effective_settings={
                "model": model,
                "temperature": request.model_defaults.temperature,
                "max_output_tokens": request.model_defaults.max_tokens,
                "timeout_seconds": timeout,
            },
            attempt_count=1 if config.max_retries == 0 else None,
            sdk_max_retries=config.max_retries,
            raw_text=_extract_output_text(response),
            valid_json=False,
            schema_valid=False,
            refusal=_extract_refusal(response),
            usage=_extract_usage(response),
            latency_ms=latency_ms,
        )


def _extract_output_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if isinstance(text, str):
        return text
    output = getattr(response, "output", None) or []
    for item in output:
        for content in getattr(item, "content", []) or []:
            candidate = getattr(content, "text", None)
            if isinstance(candidate, str):
                return candidate
    return ""


def _extract_usage(response: Any) -> dict[str, object]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        dumped = usage.model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped
    if hasattr(usage, "__dict__"):
        return dict(usage.__dict__)
    return {}


def _extract_refusal(response: Any) -> str | None:
    refusal = getattr(response, "refusal", None)
    if isinstance(refusal, str) and refusal.strip():
        return refusal
    output = getattr(response, "output", None) or []
    for item in output:
        for content in getattr(item, "content", []) or []:
            candidate = getattr(content, "refusal", None)
            if isinstance(candidate, str) and candidate.strip():
                return candidate
    return None


def _string_attribute(value: Any, name: str) -> str | None:
    candidate = getattr(value, name, None)
    return candidate if isinstance(candidate, str) and candidate else None


def _extract_finish_reason(response: Any) -> str | None:
    incomplete = getattr(response, "incomplete_details", None)
    reason = getattr(incomplete, "reason", None)
    if isinstance(reason, str) and reason:
        return reason
    return None


def _openai_sdk_version() -> str | None:
    try:
        return version("openai")
    except PackageNotFoundError:
        return None


def _build_structured_request_kwargs(*, request: LLMStructuredRequest, model: str) -> dict[str, object]:
    """Build OpenAI Responses API request kwargs for strict structured output.

    Isolated for easier compatibility updates across SDK/API shape changes.
    """
    return {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": request.system}]},
            {"role": "user", "content": [{"type": "input_text", "text": request.user}]},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "memorii_structured_output",
                "strict": True,
                "schema": request.output_schema,
            }
        },
        "temperature": request.model_defaults.temperature,
        "max_output_tokens": request.model_defaults.max_tokens,
    }
