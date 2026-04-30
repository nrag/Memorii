from __future__ import annotations

import json
from pathlib import Path

import pytest

from memorii.core.belief.models import BeliefUpdateContext
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_decision.adapters import LLMBeliefUpdateAdapter, LLMJudgeDecisionAdapter, LLMPromotionDecisionAdapter
from memorii.core.llm_judge.models import JudgeDimension, JudgeRubric
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.prompts.registry import PromptRegistry
from memorii.core.promotion.models import PromotionCandidateType, PromotionContext
from memorii.core.solver.abstention import SolverDecision

PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"
_PROMOTION_VALID = '{"promote": false, "target_plane": null, "rationale": "x", "confidence": 0.5, "failure_mode": null, "requires_judge_review": false}'
_BELIEF_VALID = '{"belief": 0.42, "confidence": 0.7, "rationale": "evidence", "failure_mode": null, "requires_judge_review": false}'
_JUDGE_VALID = '{"passed": true, "score": 0.9, "rationale": "ok", "failure_mode": null, "needs_human_review": false}'


def _runner(response_text: str) -> tuple[PromptLLMRunner, FakeLLMStructuredClient]:
    client = FakeLLMStructuredClient(default_response=response_text)
    return PromptLLMRunner(client=client, config=LLMRuntimeConfig(provider="none")), client


def _promotion_context() -> PromotionContext:
    return PromotionContext(
        candidate_id="cand:1",
        candidate_type=PromotionCandidateType.SEMANTIC,
        content="candidate summary",
        source_ids=["src:1"],
        created_from="observation",
    )


def _belief_context() -> BeliefUpdateContext:
    return BeliefUpdateContext(
        prior_belief=0.5,
        decision=SolverDecision.SUPPORTED,
        evidence_count=2,
        missing_evidence_count=0,
    )


def _rubric(dimension: JudgeDimension) -> JudgeRubric:
    return JudgeRubric(
        judge_id="judge:test",
        dimension=dimension,
        name="test",
        description="desc",
        score_1_anchor="good",
        score_0_5_anchor="mixed",
        score_0_anchor="bad",
    )


def test_promotion_adapter_loads_prompt_and_returns_success() -> None:
    runner, _ = _runner(_PROMOTION_VALID)
    adapter = LLMPromotionDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    result = adapter.decide(_promotion_context(), request_id="req:promotion:1")
    assert result.success is True
    assert result.request.prompt_ref == "promotion_decision:v1"


def test_promotion_adapter_request_includes_prompt_ref_and_prompt_hash() -> None:
    runner, client = _runner(_PROMOTION_VALID)
    adapter = LLMPromotionDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    adapter.decide(_promotion_context(), request_id="req:promotion:2")
    assert client.last_request is not None
    assert client.last_request.metadata["prompt_ref"] == "promotion_decision:v1"
    assert client.last_request.metadata["prompt_hash"]


def test_belief_adapter_loads_prompt_and_returns_success() -> None:
    runner, _ = _runner(_BELIEF_VALID)
    adapter = LLMBeliefUpdateAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    result = adapter.update(_belief_context(), request_id="req:belief:1")
    assert result.success is True
    assert result.request.prompt_ref == "belief_update:v1"


def test_belief_adapter_fails_schema_validation_for_invalid_output() -> None:
    runner, _ = _runner('{"belief": "bad"}')
    adapter = LLMBeliefUpdateAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    result = adapter.update(_belief_context(), request_id="req:belief:2")
    assert result.success is False
    assert result.failure_mode == "schema_validation"


def test_judge_adapter_maps_promotion_precision_rubric_to_prompt() -> None:
    runner, _ = _runner(_JUDGE_VALID)
    adapter = LLMJudgeDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    result = adapter.judge(
        rubric=_rubric(JudgeDimension.PROMOTION_PRECISION),
        input_payload={"input_payload": _promotion_context().model_dump(mode="json")},
        request_id="req:judge:1",
    )
    assert result.request.prompt_ref == "judges/promotion_precision:v1"


def test_judge_adapter_maps_memory_plane_rubric_to_prompt() -> None:
    runner, _ = _runner(_JUDGE_VALID)
    adapter = LLMJudgeDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    result = adapter.judge(
        rubric=_rubric(JudgeDimension.MEMORY_PLANE),
        input_payload={"input_payload": _promotion_context().model_dump(mode="json")},
        request_id="req:judge:2",
    )
    assert result.request.prompt_ref == "judges/memory_plane:v1"


def test_judge_adapter_rejects_unsupported_dimension_mapping() -> None:
    runner, _ = _runner(_JUDGE_VALID)
    adapter = LLMJudgeDecisionAdapter(
        runner=runner,
        registry=PromptRegistry(prompt_root=PROMPT_ROOT),
        prompt_ref_by_dimension={JudgeDimension.ATTRIBUTION: "judges/attribution:v1"},
    )
    with pytest.raises(ValueError, match="Unsupported judge dimension mapping"):
        adapter.judge(
            rubric=_rubric(JudgeDimension.TEMPORAL_VALIDITY),
            input_payload={},
            request_id="req:judge:3",
        )


def test_adapter_metadata_is_redacted_recursively_and_serialization_has_no_secret_values() -> None:
    runner, client = _runner(_PROMOTION_VALID)
    adapter = LLMPromotionDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    metadata = {"outer": {"token": "hide"}, "items": [{"cookie": "c1"}], "api_key": "k"}
    original = {"outer": {"token": "hide"}, "items": [{"cookie": "c1"}], "api_key": "k"}
    result = adapter.decide(_promotion_context(), request_id="req:promotion:3", metadata=metadata)
    assert client.last_request is not None
    assert client.last_request.metadata["api_key"] == "[REDACTED]"
    assert client.last_request.metadata["outer"]["token"] == "[REDACTED]"
    assert client.last_request.metadata["items"][0]["cookie"] == "[REDACTED]"
    assert metadata == original
    dumped = json.dumps(result.model_dump(mode="json"))
    assert "hide" not in dumped
    assert "\"c1\"" not in dumped
    assert "\"k\"" not in dumped


def test_no_live_api_key_required() -> None:
    config = LLMRuntimeConfig.from_env({"MEMORII_LLM_PROVIDER": "none"})
    assert config.has_api_key() is False
    runner = PromptLLMRunner(client=FakeLLMStructuredClient(default_response=_PROMOTION_VALID), config=config)
    adapter = LLMPromotionDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    assert adapter.decide(_promotion_context(), request_id="req:promotion:4").success is True


def test_result_serializes_with_json_model_dump() -> None:
    runner, _ = _runner(_JUDGE_VALID)
    adapter = LLMJudgeDecisionAdapter(runner=runner, registry=PromptRegistry(prompt_root=PROMPT_ROOT))
    result = adapter.judge(
        rubric=_rubric(JudgeDimension.ATTRIBUTION),
        input_payload={"source_actor": "tool"},
        request_id="req:judge:4",
    )
    dumped = result.model_dump(mode="json")
    assert isinstance(dumped, dict)
    json.dumps(dumped)
