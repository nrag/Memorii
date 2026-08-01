from __future__ import annotations

from memorii.core.benchmark.artifact_rows import SemanticDecisionAttemptRow
from memorii.core.benchmark.semantic_attempt_artifacts import (
    provider_attempt_status,
    semantic_attempt_artifact,
)
from memorii.core.llm_provider.models import (
    LLMDecisionResult,
    LLMStructuredRequest,
    LLMStructuredResponse,
)
from memorii.core.memory_evolution import ProviderAttemptStatus
from memorii.core.prompts.models import PromptModelDefaults
from pydantic import BaseModel


class _RepairRequest(BaseModel):
    violation_codes: list[str]
    previous_decision: dict[str, object]


def _request(*, request_id: str) -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id=request_id,
        prompt_ref="memory_evolution_sim_reconstruction:v1",
        prompt_hash="prompt-hash",
        system="system text containing secret-system-value",
        user="user text containing secret-user-value",
        output_schema={},
        model_defaults=PromptModelDefaults(model="test-model"),
    )


def test_schema_failure_retains_redacted_parsed_payload_without_acceptance() -> None:
    request = _request(request_id="request:primary")
    parsed = {
        "operation": "answer",
        "api_key": "secret-provider-value",
    }
    result = LLMDecisionResult(
        request=request,
        response=LLMStructuredResponse(
            request_id=request.request_id,
            provider="fake",
            requested_model="test-model",
            actual_model="test-model-build",
            provider_request_id="provider-request",
            raw_text='{"api_key":"secret-provider-value"}',
            parsed_json=parsed,
            valid_json=True,
            schema_valid=False,
        ),
        output=None,
        success=False,
        failure_mode="schema_validation",
    )

    status = provider_attempt_status(result)
    row = semantic_attempt_artifact(
        attempt=0,
        result=result,
        provider_status=status,
        accepted=False,
        failure_mode="schema_validation",
        validation_issues=[],
        compiled_output=None,
    )
    serialized = row.model_dump_json()

    assert status == ProviderAttemptStatus.SCHEMA_ERROR
    assert row.schema_validation_status == "failed"
    assert row.semantic_validation_status == "not_evaluated"
    assert row.semantic_output == {
        "operation": "answer",
        "api_key": "[REDACTED]",
    }
    assert SemanticDecisionAttemptRow.model_validate_json(serialized) == row
    for secret in (
        "secret-provider-value",
        "secret-system-value",
        "secret-user-value",
    ):
        assert secret not in serialized


def test_repair_attempt_round_trip_preserves_binding_and_compiled_output() -> None:
    request = _request(request_id="request:repair")
    semantic_output = {
        "operation": "abstain",
        "claim_assessments": [],
    }
    result = LLMDecisionResult(
        request=request,
        response=LLMStructuredResponse(
            request_id=request.request_id,
            provider="fake",
            requested_model="test-model",
            actual_model="test-model-build",
            provider_request_id="provider-request",
            raw_text="not retained",
            parsed_json=semantic_output,
            valid_json=True,
            schema_valid=True,
        ),
        output=semantic_output,
        success=True,
    )
    compiled_output = {
        "operation": "abstain",
        "selected_claim_ids": [],
    }
    repair_request = _RepairRequest(
        violation_codes=["missing_claim_assessment"],
        previous_decision={"operation": "answer", "claim_assessments": []},
    )

    row = semantic_attempt_artifact(
        attempt=1,
        result=result,
        provider_status=provider_attempt_status(result),
        accepted=True,
        failure_mode=None,
        validation_issues=[],
        compiled_output=compiled_output,
        repair_request=repair_request,
    )
    round_tripped = SemanticDecisionAttemptRow.model_validate_json(
        row.model_dump_json()
    )

    assert round_tripped == row
    assert round_tripped.request_id == "request:repair"
    assert round_tripped.prompt_ref == "memory_evolution_sim_reconstruction:v1"
    assert round_tripped.prompt_hash == "prompt-hash"
    assert round_tripped.provider_request_id == "provider-request"
    assert round_tripped.repair_request == repair_request.model_dump(mode="json")
    assert round_tripped.previous_decision_digest is not None
    assert round_tripped.compiled_output == compiled_output
