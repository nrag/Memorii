from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


def _result(success: bool=True):
    req=LLMStructuredRequest(request_id='req/1',prompt_ref='promotion_decision:v1',prompt_hash='h1',system='s',user='u',output_schema={},model_defaults={},metadata={'token':'x'})
    res=LLMStructuredResponse(request_id='req/1',provider='openai',model='gpt',raw_text='{"a":1}',parsed_json={'a':1},valid_json=True,schema_valid=success,usage={'prompt_tokens':1},latency_ms=7,error=None if success else 'boom')
    return LLMDecisionResult(request=req,response=res,output={'a':1} if success else None,success=success,failure_mode=None if success else 'provider_error')


def test_builder_success_and_failed_and_redaction() -> None:
    t=build_llm_decision_trace_from_result(decision_point=LLMDecisionPoint.PROMOTION, mode=LLMDecisionMode.LLM, result=_result(True), final_output=None, fallback_used=False, metadata={'password':'p','nested':{'api_key':'k'}})
    assert 'req_1' in t.trace_id
    assert t.parsed_output == {'a':1}
    dumped=t.model_dump_json()
    assert '"[REDACTED]"' in dumped and '"k"' not in dumped and '"p"' not in dumped
    m=t.final_output['_response_meta']
    assert m['provider']=='openai' and m['model']=='gpt' and m['usage']=={'prompt_tokens':1} and m['latency_ms']==7
    f=build_llm_decision_trace_from_result(decision_point=LLMDecisionPoint.BELIEF_UPDATE, mode=LLMDecisionMode.LLM, result=_result(False), final_output=None, fallback_used=True)
    assert f.fallback_used is True
