from __future__ import annotations

import time
from typing import Any

from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.models import LLMStructuredRequest, LLMStructuredResponse


class OpenAIStructuredClient:
    provider_name = "openai"

    def complete_structured(self, request: LLMStructuredRequest, *, config: LLMRuntimeConfig) -> LLMStructuredResponse:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("OpenAI SDK is required for OpenAIStructuredClient. Install the openai extra.") from exc

        api_key = config.require_api_key().get_secret_value()
        model = request.model_defaults.model or config.model or "gpt-4.1-mini"
        timeout = request.model_defaults.timeout_seconds or config.timeout_seconds
        client = OpenAI(api_key=api_key, timeout=timeout, max_retries=config.max_retries)

        started = time.perf_counter()
        response = client.responses.create(**_build_structured_request_kwargs(request=request, model=model))
        latency_ms = int((time.perf_counter() - started) * 1000)

        return LLMStructuredResponse(
            request_id=request.request_id,
            provider=self.provider_name,
            model=model,
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
    }
