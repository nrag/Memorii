from __future__ import annotations

import re
from datetime import UTC, datetime

from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_provider.models import LLMDecisionResult

_SECRET_KEYS = {"api_key", "apikey", "token", "password", "secret", "authorization", "cookie"}


def _redact(value: object) -> object:
    if isinstance(value, dict):
        out: dict[str, object] = {}
        for k, v in value.items():
            if k.lower() in _SECRET_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def _sanitize_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]", "_", value)


def build_llm_decision_trace_from_result(*, decision_point: LLMDecisionPoint, mode: LLMDecisionMode, result: LLMDecisionResult, final_output: dict[str, object] | None, fallback_used: bool, metadata: dict[str, object] | None = None) -> LLMDecisionTrace:
    status = LLMDecisionStatus.SUCCEEDED if result.success else LLMDecisionStatus.PROVIDER_ERROR
    input_payload = {
        "prompt_ref": result.request.prompt_ref,
        "prompt_hash": result.request.prompt_hash,
        "request_id": result.request.request_id,
        "provider": result.response.provider,
        "model": result.response.model,
        "metadata": _redact(metadata or result.request.metadata),
    }
    parsed_output = result.output or {}
    final = final_output or result.output or {}
    safe_raw = None
    return LLMDecisionTrace(
        trace_id=f"trace:llm:{_sanitize_id(result.request.request_id)}",
        decision_point=decision_point,
        mode=mode,
        prompt_version=result.request.prompt_ref,
        model_name=result.response.model,
        input_payload=input_payload,
        raw_output=safe_raw,
        parsed_output=parsed_output,
        validation_errors=[result.failure_mode] if result.failure_mode else [],
        fallback_used=fallback_used,
        final_output={**final, "_response_meta": _redact({"provider": result.response.provider, "model": result.response.model, "valid_json": result.response.valid_json, "schema_valid": result.response.schema_valid, "refusal": result.response.refusal, "error": result.response.error, "usage": result.response.usage, "latency_ms": result.response.latency_ms, "failure_mode": result.failure_mode})},
        status=status,
        created_at=datetime.now(UTC),
    )
