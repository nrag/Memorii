from __future__ import annotations

import re
from datetime import UTC, datetime

from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.prompts.sensitivity import redact_sensitive_value


def _sanitize_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.:-]", "_", value)


def build_llm_decision_trace_from_result(*, decision_point: LLMDecisionPoint, mode: LLMDecisionMode, result: LLMDecisionResult, final_output: dict[str, object] | None, fallback_used: bool, metadata: dict[str, object] | None = None, status: LLMDecisionStatus | None = None) -> LLMDecisionTrace:
    resolved_status = status or (LLMDecisionStatus.SUCCEEDED if result.success else LLMDecisionStatus.PROVIDER_ERROR)
    response_meta = redact_sensitive_value({
        "provider": result.response.provider,
        "requested_model": result.response.requested_model,
        "actual_model": result.response.actual_model,
        "provider_request_id": result.response.provider_request_id,
        "response_status": result.response.response_status,
        "finish_reason": result.response.finish_reason,
        "sdk_version": result.response.sdk_version,
        "effective_settings": result.response.effective_settings,
        "attempt_count": result.response.attempt_count,
        "sdk_max_retries": result.response.sdk_max_retries,
        "valid_json": result.response.valid_json,
        "schema_valid": result.response.schema_valid,
        "refusal": result.response.refusal,
        "error": result.response.error,
        "usage": result.response.usage,
        "latency_ms": result.response.latency_ms,
        "failure_mode": result.failure_mode,
    })
    input_payload = {
        "prompt_ref": result.request.prompt_ref,
        "prompt_hash": result.request.prompt_hash,
        "request_id": result.request.request_id,
        "provider": result.response.provider,
        "requested_model": result.response.requested_model,
        "actual_model": result.response.actual_model,
        "metadata": redact_sensitive_value(metadata or result.request.metadata),
        "response_meta": response_meta,
    }
    return LLMDecisionTrace(
        trace_id=f"trace:llm:{_sanitize_id(result.request.request_id)}",
        decision_point=decision_point,
        mode=mode,
        prompt_version=result.request.prompt_ref,
        model_name=result.response.actual_model or result.response.requested_model,
        input_payload=input_payload,
        raw_output=None,
        parsed_output=result.output or {},
        validation_errors=[result.failure_mode] if result.failure_mode else [],
        fallback_used=fallback_used,
        final_output=final_output or result.output or {},
        status=resolved_status,
        created_at=datetime.now(UTC),
    )
