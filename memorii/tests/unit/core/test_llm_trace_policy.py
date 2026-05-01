import pytest
from pydantic import ValidationError

from memorii.core.llm_trace.policy import LLMTracePolicy


def test_default_does_not_persist_clean_success() -> None:
    assert not LLMTracePolicy().should_persist(llm_used=True, llm_success=True, fallback_used=False, disagreement=False, requires_judge_review=False)

def test_trace_successes_persists_clean_success() -> None:
    assert LLMTracePolicy(trace_successes=True).should_persist(llm_used=True, llm_success=True, fallback_used=False, disagreement=False, requires_judge_review=False)

def test_default_failure_fallback_disagreement_review_and_min_score() -> None:
    p=LLMTracePolicy()
    assert p.should_persist(llm_used=True,llm_success=False,fallback_used=False,disagreement=False,requires_judge_review=False)
    assert p.should_persist(llm_used=False,llm_success=None,fallback_used=True,disagreement=False,requires_judge_review=False)
    assert p.should_persist(llm_used=False,llm_success=None,fallback_used=False,disagreement=True,requires_judge_review=False)
    assert p.should_persist(llm_used=False,llm_success=None,fallback_used=False,disagreement=False,requires_judge_review=True)
    assert LLMTracePolicy(min_judge_score_to_keep=0.3).should_persist(llm_used=False,llm_success=None,fallback_used=False,disagreement=False,requires_judge_review=False,judge_score=0.2)

def test_extra_and_invalid_rejected() -> None:
    with pytest.raises(ValidationError):
        LLMTracePolicy(bad=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        LLMTracePolicy(min_judge_score_to_keep=2.0)
