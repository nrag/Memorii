from datetime import UTC, datetime

import pytest
from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result
from memorii.core.llm_validation import LLMValidationIssue, LLMValidationStage


def _result(success: bool=True):
    req=LLMStructuredRequest(request_id='req/1',prompt_ref='promotion_decision:v1',prompt_hash='h1',system='s',user='u',output_schema={},model_defaults={},metadata={'token':'x'})
    res=LLMStructuredResponse(request_id='req/1',provider='openai',requested_model='gpt',actual_model='gpt',raw_text='{"a":1}',parsed_json={'a':1},valid_json=True,schema_valid=success,usage={'prompt_tokens':1},latency_ms=7,error=None if success else 'boom')
    return LLMDecisionResult(request=req,response=res,output={'a':1} if success else None,success=success,failure_mode=None if success else 'provider_error')


def test_builder_success_and_failed_and_redaction() -> None:
    t=build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.PROMOTION,
        mode=LLMDecisionMode.LLM,
        result=_result(True),
        final_output=None,
        fallback_used=False,
        metadata={
            'Pass-Word': 'p',
            'nested': {
                'ＡＰＩ＿ＫＥＹ': 'k',
                'items': ({'Auth orization': 'bearer'},),
            },
        },
    )
    assert 'req_1' in t.trace_id
    assert t.parsed_output == {'a':1}
    dumped=t.model_dump_json()
    assert '"[REDACTED]"' in dumped
    assert all(secret not in dumped for secret in ('"k"', '"p"', '"bearer"'))
    m=t.input_payload['response_meta']
    assert m['provider']=='openai' and m['requested_model']=='gpt' and m['actual_model']=='gpt'
    assert m['usage']=={'prompt_tokens':1} and m['latency_ms']==7
    f=build_llm_decision_trace_from_result(decision_point=LLMDecisionPoint.BELIEF_UPDATE, mode=LLMDecisionMode.LLM, result=_result(False), final_output=None, fallback_used=True)
    assert f.fallback_used is True
    assert f.status == LLMDecisionStatus.FALLBACK_USED


def test_builder_preserves_rejected_candidate_and_typed_semantic_issues() -> None:
    result = _result(False).model_copy(
        update={
            "failure_mode": "semantic_validation",
            "rejected_output": {
                "selected_candidate_ids": ["candidate-1"],
                "api_key": "must-not-survive",
            },
            "validation_issues": [
                LLMValidationIssue(
                    stage=LLMValidationStage.SEMANTIC,
                    code="value_error",
                    location=("proof_steps", 0, "citations"),
                    message="Field required",
                )
            ],
        }
    )

    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.EVIDENCE_SELECTION,
        mode=LLMDecisionMode.LLM,
        result=result,
        final_output=None,
        fallback_used=False,
    )

    assert trace.status == LLMDecisionStatus.VALIDATION_FAILED
    assert trace.parsed_output is None
    assert trace.rejected_output == {
        "selected_candidate_ids": ["candidate-1"],
        "api_key": "[REDACTED]",
    }
    assert trace.validation_issues == result.validation_issues
    dumped = trace.model_dump_json()
    assert result.response.raw_text not in dumped


def test_trace_rejects_candidate_that_is_both_accepted_and_rejected() -> None:
    issue = LLMValidationIssue(
        stage=LLMValidationStage.SEMANTIC,
        code="value_error",
        location=("selected_candidate_ids",),
        message="candidate failed semantic validation",
    )

    with pytest.raises(
        ValueError,
        match="rejected output cannot also be accepted parsed output",
    ):
        LLMDecisionTrace(
            trace_id="trace:contradictory",
            decision_point=LLMDecisionPoint.EVIDENCE_SELECTION,
            mode=LLMDecisionMode.LLM,
            input_payload={},
            parsed_output={"selected_candidate_ids": ["candidate-1"]},
            rejected_output={"selected_candidate_ids": ["candidate-1"]},
            validation_issues=[issue],
            final_output={},
            status=LLMDecisionStatus.VALIDATION_FAILED,
            created_at=datetime.now(UTC),
        )
