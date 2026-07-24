"""Construction of secret-free semantic-attempt benchmark evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from memorii.core.benchmark.artifact_rows import (
    ArtifactJsonObject,
    SemanticDecisionAttemptRow,
)
from memorii.core.benchmark.reproducibility import canonical_json_digest
from memorii.core.llm_provider.models import LLMDecisionResult
from memorii.core.memory_evolution.models import ProviderAttemptStatus
from memorii.core.prompts.sensitivity import redact_sensitive_value


def provider_attempt_status(result: LLMDecisionResult) -> ProviderAttemptStatus:
    """Classify transport and schema outcome from provider evidence."""

    if result.failure_mode == "provider_error":
        return ProviderAttemptStatus.PROVIDER_ERROR
    if not result.response.valid_json:
        return ProviderAttemptStatus.INVALID_JSON
    if not result.response.schema_valid or result.output is None:
        return ProviderAttemptStatus.SCHEMA_ERROR
    return ProviderAttemptStatus.SUCCEEDED


def semantic_attempt_artifact(
    *,
    attempt: int,
    result: LLMDecisionResult,
    provider_status: ProviderAttemptStatus,
    accepted: bool,
    failure_mode: str | None,
    validation_issues: list[str],
    compiled_output: dict[str, object] | None,
    repair_request: BaseModel | None = None,
) -> SemanticDecisionAttemptRow:
    """Build one auditable attempt without persisting prompts or raw text."""

    semantic_payload = (
        result.output
        if result.output is not None
        else result.rejected_output
        if result.rejected_output is not None
        else result.response.parsed_json
    )
    repair_payload = repair_request.model_dump(mode="json") if repair_request is not None else None
    previous_decision = (
        repair_payload.get("previous_decision")
        if isinstance(repair_payload, dict)
        else None
    )
    return SemanticDecisionAttemptRow(
        attempt=attempt,
        request_id=result.request.request_id,
        prompt_ref=result.request.prompt_ref,
        prompt_hash=result.request.prompt_hash,
        provider=result.response.provider,
        requested_model=result.response.requested_model,
        actual_model=result.response.actual_model,
        provider_request_id=result.response.provider_request_id,
        provider_attempt_status=provider_status,
        schema_validation_status=_schema_validation_status(result),
        semantic_validation_status=(
            "passed"
            if accepted
            else "failed"
            if provider_status == ProviderAttemptStatus.SUCCEEDED
            else "not_evaluated"
        ),
        semantic_output=_artifact_payload(semantic_payload),
        compiled_output=_artifact_payload(compiled_output if accepted else None),
        repair_request=_artifact_payload(repair_payload),
        previous_decision_digest=(
            canonical_json_digest(previous_decision)
            if previous_decision is not None
            else None
        ),
        accepted=accepted,
        failure_mode=failure_mode,
        validation_issues=validation_issues,
    )


def _schema_validation_status(
    result: LLMDecisionResult,
) -> Literal["not_evaluated", "passed", "failed"]:
    if not result.response.valid_json:
        return "not_evaluated"
    return "passed" if result.response.schema_valid else "failed"


def _artifact_payload(value: object | None) -> ArtifactJsonObject | None:
    if value is None:
        return None
    redacted = redact_sensitive_value(value)
    if not isinstance(redacted, dict):
        raise TypeError("semantic attempt payload must remain a JSON object")
    return ArtifactJsonObject(root=redacted)
