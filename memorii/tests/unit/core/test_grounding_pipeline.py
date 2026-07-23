from __future__ import annotations

from typing import Any

import pytest
from memorii.core.grounding.models import (
    AlternativeAnswerCheck,
    AnswerRequirement,
    AnswerVerificationDecision,
    CandidateAnswerConsidered,
    CandidateRequirementCoverage,
    EvidenceCandidate,
    EvidenceSelectionContext,
    EvidenceSelectionDecision,
    GroundedAnswerDecision,
    ProofStep,
    ProofStepCitation,
    QuestionConstraintCoverage,
)
from memorii.core.grounding.pipeline import (
    GroundedAnswerPipeline,
    fake_llm_result_for_answer_verification,
    fake_llm_result_for_evidence_selection,
    fake_llm_result_for_grounded_answer,
    finalize_answer,
    reconcile_provenance,
)
from memorii.core.llm_decision.models import LLMDecisionMode
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.prompts.models import PromptModelDefaults


def _context() -> EvidenceSelectionContext:
    return EvidenceSelectionContext(
        query="Who wrote notes on the Analytical Engine?",
        candidates=[
            EvidenceCandidate(
                candidate_id="ev1",
                title="Ada Lovelace",
                text="Ada Lovelace wrote notes on the Analytical Engine.",
            ),
            EvidenceCandidate(
                candidate_id="ev2",
                title="Charles Babbage",
                text="Charles Babbage designed the Analytical Engine.",
            ),
        ],
    )


def _long_id_context() -> EvidenceSelectionContext:
    return EvidenceSelectionContext(
        query="Who wrote notes on the Analytical Engine?",
        candidates=[
            EvidenceCandidate(
                candidate_id="hotpotqa:example-with-long-id:paragraph-0001:sentence-0001",
                title="Ada Lovelace",
                text="Ada Lovelace wrote notes on the Analytical Engine.",
                metadata={"source_candidate_id": "hotpotqa:example-with-long-id:paragraph-0001:sentence-0001"},
            ),
            EvidenceCandidate(
                candidate_id="hotpotqa:example-with-long-id:paragraph-0002:sentence-0001",
                title="Charles Babbage",
                text="Charles Babbage designed the Analytical Engine.",
            ),
        ],
    )


def _three_evidence() -> list[EvidenceCandidate]:
    return [
        EvidenceCandidate(candidate_id="ev1", title="Bridge A", text="Ada Lovelace wrote notes."),
        EvidenceCandidate(candidate_id="ev2", title="Bridge B", text="The notes were about the Analytical Engine."),
        EvidenceCandidate(candidate_id="ev3", title="Answer", text="Ada Lovelace wrote notes on the Analytical Engine."),
    ]


def _request(request_id: str, prompt_ref: str, metadata: dict[str, object] | None = None) -> LLMStructuredRequest:
    return LLMStructuredRequest(
        request_id=request_id,
        prompt_ref=prompt_ref,
        prompt_hash="test",
        system="",
        user="",
        output_schema={},
        model_defaults=PromptModelDefaults(provider="none"),
        metadata=metadata or {},
    )


def _constraint(
    candidate_ids: list[str],
    *,
    constraint_id: str = "constraint:1",
    satisfied: bool = True,
    description: str = "The answer must satisfy the question constraints.",
) -> QuestionConstraintCoverage:
    return QuestionConstraintCoverage(
        constraint_id=constraint_id,
        description=description,
        satisfied=satisfied,
        candidate_ids=candidate_ids,
        rationale="test constraint coverage",
    )


def _requirement(requirement_id: str, candidate_ids: list[str]) -> AnswerRequirement:
    return AnswerRequirement(
        requirement_id=requirement_id,
        description=f"Requirement {requirement_id}",
        requirement_type="direct_answer",
        candidate_ids=candidate_ids,
        rationale="test requirement",
    )


def _coverage(requirement_id: str, candidate_ids: list[str], *, satisfied: bool = True) -> CandidateRequirementCoverage:
    return CandidateRequirementCoverage(
        requirement_id=requirement_id,
        satisfied=satisfied,
        candidate_ids=candidate_ids,
        rationale="test candidate coverage",
    )


def _proof_step(
    *,
    step_id: str,
    description: str,
    candidate_ids: list[str],
    rationale: str,
    required_candidate_ids: list[str] | None = None,
    final_support_ids: list[str] | None = None,
) -> ProofStep:
    unique_ids = list(dict.fromkeys(candidate_ids))
    required_ids = unique_ids if required_candidate_ids is None else required_candidate_ids
    final_ids = set(unique_ids if final_support_ids is None else final_support_ids)
    return ProofStep(
        step_id=step_id,
        description=description,
        candidate_ids=candidate_ids,
        required_candidate_ids=required_ids,
        citations=[
            ProofStepCitation(
                candidate_id=candidate_id,
                role="direct_answer",
                required_for_final_support=candidate_id in final_ids,
                claim_supported=description,
                rationale=rationale,
            )
            for candidate_id in unique_ids
        ],
        rationale=rationale,
    )


def _grounded_answer(
    *,
    answer: str = "Ada Lovelace",
    citation_candidate_ids: list[str],
    answer_span_candidate_id: str | None = None,
    rationale: str,
) -> GroundedAnswerDecision:
    requirement = _requirement("requirement:direct-answer", citation_candidate_ids)
    return GroundedAnswerDecision(
        answer=answer,
        citation_candidate_ids=citation_candidate_ids,
        answer_requirements=[requirement],
        candidate_answers_considered=[
            CandidateAnswerConsidered(
                answer=answer,
                candidate_ids=citation_candidate_ids,
                selected=True,
                answer_type="entity",
                requirement_coverage=[_coverage(requirement.requirement_id, citation_candidate_ids)],
                satisfied_requirement_ids=[requirement.requirement_id],
                missing_requirement_ids=[],
                rationale=rationale,
            )
        ],
        answer_type="entity",
        answer_span_candidate_id=answer_span_candidate_id or citation_candidate_ids[0],
        answer_span_text=answer,
        confidence=0.9,
        rationale=rationale,
        failure_mode=None,
        requires_judge_review=False,
    )


class _EvidenceAdapter:
    def decide(self, context: EvidenceSelectionContext, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.candidates] == ["e1", "e2"]
        assert metadata is not None
        assert metadata["candidate_id_aliases"] == {"e1": "ev1", "e2": "ev2"}
        return fake_llm_result_for_evidence_selection(
            request=_request(request_id, "evidence_selection:v1", metadata=metadata),
            decision=EvidenceSelectionDecision(
                selected_candidate_ids=["e1"],
                excluded_candidate_ids=["e2"],
                ranking=["e1", "e2"],
                proof_steps=[
                    _proof_step(
                        step_id="step:1",
                        description="Find the direct author evidence.",
                        candidate_ids=["e1"],
                        rationale="ev1 directly answers the query.",
                    )
                ],
                confidence=0.9,
                rationale="direct evidence",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _LongIdEvidenceAdapter:
    def decide(self, context: EvidenceSelectionContext, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.candidates] == ["e1", "e2"]
        assert context.candidates[0].metadata["source_candidate_id"] == "e1"
        assert metadata is not None
        assert metadata["candidate_id_aliases"] == {
            "e1": "hotpotqa:example-with-long-id:paragraph-0001:sentence-0001",
            "e2": "hotpotqa:example-with-long-id:paragraph-0002:sentence-0001",
        }
        return fake_llm_result_for_evidence_selection(
            request=_request(request_id, "evidence_selection:v1", metadata=metadata),
            decision=EvidenceSelectionDecision(
                selected_candidate_ids=["e1"],
                excluded_candidate_ids=["e2"],
                ranking=["e1", "e2"],
                proof_steps=[
                    _proof_step(
                        step_id="step:1",
                        description="Find the direct author evidence.",
                        candidate_ids=["e1"],
                        rationale="e1 directly answers the query.",
                    )
                ],
                confidence=0.9,
                rationale="direct evidence",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _TwoEvidenceAdapter:
    def decide(self, context: EvidenceSelectionContext, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.candidates] == ["e1", "e2"]
        assert metadata is not None
        assert metadata["candidate_id_aliases"] == {"e1": "ev1", "e2": "ev2"}
        return fake_llm_result_for_evidence_selection(
            request=_request(request_id, "evidence_selection:v1", metadata=metadata),
            decision=EvidenceSelectionDecision(
                selected_candidate_ids=["e2", "e1"],
                excluded_candidate_ids=[],
                ranking=["e1", "e2"],
                proof_steps=[
                    _proof_step(
                        step_id="step:1",
                        description="Identify the note author.",
                        candidate_ids=["e1", "e2", "e1"],
                        final_support_ids=[],
                        rationale="Both candidates are part of the proof; duplicates should be flattened.",
                    )
                ],
                confidence=0.9,
                rationale="multi-evidence proof",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _AnswerAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] in (["e1"], ["e1", "e2"])
        assert metadata is not None
        assert "candidate_id_aliases" in metadata
        return fake_llm_result_for_grounded_answer(
            request=_request(request_id, "grounded_answer:v1", metadata=metadata),
            decision=_grounded_answer(citation_candidate_ids=["e1"], rationale="supported"),
        )


class _InvalidAnswerSpanAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_grounded_answer(
            request=_request(request_id, "grounded_answer:v1", metadata=metadata),
            decision=_grounded_answer(
                citation_candidate_ids=["e1"],
                answer_span_candidate_id="e9",
                rationale="invalid span candidate id",
            ),
        )


class _AnswerSecondEvidenceAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] == ["e1", "e2"]
        assert metadata is not None
        assert metadata["candidate_id_aliases"] == {"e1": "ev1", "e2": "ev2"}
        return fake_llm_result_for_grounded_answer(
            request=_request(request_id, "grounded_answer:v1", metadata=metadata),
            decision=_grounded_answer(
                citation_candidate_ids=["e2"],
                rationale="answerer cited a related evidence item",
            ),
        )


class _RepairingVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] == ["e1", "e2"]
        assert metadata is not None
        assert metadata["candidate_id_aliases"] == {"e1": "ev1", "e2": "ev2"}
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=["e1", "e2"],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e1", "e2"])],
                confidence=0.9,
                rationale="both evidence items are needed",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _InvalidCitationVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=["e3"],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e3"])],
                confidence=0.9,
                rationale="invalid citation id",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _NonEntailedVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=False,
                corrected_answer="Charles Babbage",
                required_candidate_ids=["e2"],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e2"], satisfied=False)],
                confidence=0.9,
                rationale="answer is not entailed",
                failure_mode="not_entailed",
                requires_judge_review=True,
            ),
        )


class _EmptyCitationVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=[],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e1", "e2"])],
                confidence=0.9,
                rationale="entailed but verifier did not provide minimal citations",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _VerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert metadata is not None
        assert "candidate_id_aliases" in metadata
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=["e1"],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e1"])],
                confidence=0.9,
                rationale="entailed",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _UncoveredConstraintVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=["e1"],
                missing_candidate_ids=[],
                question_constraints=[
                    _constraint(
                        ["e1"],
                        constraint_id="constraint:bridge_entity",
                        satisfied=False,
                        description="The answer must satisfy the bridge entity constraint.",
                    )
                ],
                confidence=0.9,
                rationale="answer string is supported, but a question constraint is not covered",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _MissingConstraintsVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=["e1"],
                missing_candidate_ids=[],
                question_constraints=[],
                confidence=0.9,
                rationale="legacy verifier output without explicit constraint coverage",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _BetterAlternativeVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=True,
                corrected_answer=None,
                required_candidate_ids=["e1"],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e1"])],
                alternative_answers=[
                    AlternativeAnswerCheck(
                        answer="Charles Babbage",
                        candidate_ids=["e2"],
                        satisfies_question_constraints=True,
                        better_than_proposed_answer=True,
                        rationale="The alternative satisfies the question constraints better.",
                    )
                ],
                confidence=0.9,
                rationale="proposed answer has a better alternative",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _MissingRequirementAnswerAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] == ["e1", "e2"]
        requirements = [_requirement("r1", ["e1"]), _requirement("r2", ["e2"])]
        return fake_llm_result_for_grounded_answer(
            request=_request(request_id, "grounded_answer:v1", metadata=metadata),
            decision=GroundedAnswerDecision(
                answer="Ada Lovelace",
                citation_candidate_ids=["e1"],
                answer_requirements=requirements,
                candidate_answers_considered=[
                    CandidateAnswerConsidered(
                        answer="Ada Lovelace",
                        candidate_ids=["e1"],
                        selected=True,
                        answer_type="entity",
                        requirement_coverage=[_coverage("r1", ["e1"]), _coverage("r2", [], satisfied=False)],
                        satisfied_requirement_ids=["r1"],
                        missing_requirement_ids=["r2"],
                        rationale="selected answer misses one requirement",
                    )
                ],
                answer_type="entity",
                answer_span_candidate_id="e1",
                answer_span_text="Ada Lovelace",
                confidence=0.9,
                rationale="selected answer is incomplete",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _BetterCoverageAnswerAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] == ["e1", "e2"]
        requirements = [_requirement("r1", ["e1"]), _requirement("r2", ["e2"])]
        return fake_llm_result_for_grounded_answer(
            request=_request(request_id, "grounded_answer:v1", metadata=metadata),
            decision=GroundedAnswerDecision(
                answer="Ada Lovelace",
                citation_candidate_ids=["e1"],
                answer_requirements=requirements,
                candidate_answers_considered=[
                    CandidateAnswerConsidered(
                        answer="Ada Lovelace",
                        candidate_ids=["e1"],
                        selected=True,
                        answer_type="entity",
                        requirement_coverage=[_coverage("r1", ["e1"])],
                        satisfied_requirement_ids=["r1"],
                        missing_requirement_ids=[],
                        rationale="selected candidate has weaker coverage",
                    ),
                    CandidateAnswerConsidered(
                        answer="Charles Babbage",
                        candidate_ids=["e1", "e2"],
                        selected=False,
                        answer_type="entity",
                        requirement_coverage=[_coverage("r1", ["e1"]), _coverage("r2", ["e2"])],
                        satisfied_requirement_ids=["r1", "r2"],
                        missing_requirement_ids=[],
                        rationale="alternative satisfies more requirements",
                    ),
                ],
                answer_type="entity",
                answer_span_candidate_id="e1",
                answer_span_text="Ada Lovelace",
                confidence=0.9,
                rationale="selected answer is weaker than an alternative",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _GuardedCorrectionAnswerAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] == ["e1", "e2"]
        requirements = [_requirement("r1", ["e2"])]
        return fake_llm_result_for_grounded_answer(
            request=_request(request_id, "grounded_answer:v1", metadata=metadata),
            decision=GroundedAnswerDecision(
                answer="Ada Lovelace",
                citation_candidate_ids=["e1"],
                answer_requirements=requirements,
                candidate_answers_considered=[
                    CandidateAnswerConsidered(
                        answer="Ada Lovelace",
                        candidate_ids=["e1"],
                        selected=True,
                        answer_type="entity",
                        requirement_coverage=[_coverage("r1", [], satisfied=False)],
                        satisfied_requirement_ids=[],
                        missing_requirement_ids=["r1"],
                        rationale="selected answer is locally supported but misses the required relation",
                    ),
                    CandidateAnswerConsidered(
                        answer="Charles Babbage",
                        candidate_ids=["e2"],
                        selected=False,
                        answer_type="entity",
                        requirement_coverage=[_coverage("r1", ["e2"])],
                        satisfied_requirement_ids=["r1"],
                        missing_requirement_ids=[],
                        rationale="alternative satisfies the required relation",
                    ),
                ],
                answer_type="entity",
                answer_span_candidate_id="e1",
                answer_span_text="Ada Lovelace",
                confidence=0.9,
                rationale="selected answer is weaker than a supported alternative",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _GuardedCorrectionVerificationAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        assert [candidate.candidate_id for candidate in context.evidence] == ["e1", "e2"]
        return fake_llm_result_for_answer_verification(
            request=_request(request_id, "answer_verification:v1", metadata=metadata),
            decision=AnswerVerificationDecision(
                entailed=False,
                corrected_answer="Charles Babbage",
                required_candidate_ids=["e2"],
                missing_candidate_ids=[],
                question_constraints=[_constraint(["e2"], satisfied=False)],
                alternative_answers=[
                    AlternativeAnswerCheck(
                        answer="Charles Babbage",
                        candidate_ids=["e2"],
                        satisfies_question_constraints=True,
                        better_than_proposed_answer=True,
                        satisfied_requirement_ids=["r1"],
                        missing_requirement_ids=[],
                        rationale="The alternative is the only candidate satisfying the required relation.",
                    )
                ],
                confidence=0.9,
                rationale="proposed answer is not the best supported answer",
                failure_mode=None,
                requires_judge_review=False,
            ),
        )


class _InvalidAdapter:
    def decide(self, context: Any, *, request_id: str, metadata: dict[str, object] | None = None) -> LLMDecisionResult:
        del context, metadata
        response = LLMStructuredResponse(
            request_id=request_id,
            provider="fake-invalid",
            raw_text="{}",
            parsed_json={},
            valid_json=True,
            schema_valid=False,
        )
        return LLMDecisionResult(
            request=_request(request_id, "invalid:v1"),
            response=response,
            output={},
            success=False,
            failure_mode="schema_validation",
        )


def test_grounded_answer_pipeline_rule_path_runs_without_llm() -> None:
    result = GroundedAnswerPipeline(mode=LLMDecisionMode.RULE).run(
        _context(),
        request_id_prefix="req:grounding:rule",
    )

    assert result.selected_candidate_ids
    assert result.answer
    assert result.traces
    assert result.fallback_used is False


def test_grounded_answer_pipeline_llm_path_records_three_successful_traces() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_EvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:llm")

    assert result.success is True
    assert result.answer == "Ada Lovelace"
    assert result.selected_candidate_ids == ["ev1"]
    assert result.proof_citation_candidate_ids == ["ev1"]
    assert result.citation_candidate_ids == ["ev1"]
    assert result.answer_citation_candidate_ids == ["ev1"]
    assert result.verified_citation_candidate_ids == ["ev1"]
    assert result.evidence_selection.proof_steps
    assert result.answer_verification.alternative_answers == []
    assert len(result.traces) == 3
    assert all(trace.fallback_used is False for trace in result.traces)
    assert result.traces[0].input_payload["metadata"]["candidate_id_aliases"] == {"e1": "ev1", "e2": "ev2"}
    assert result.traces[0].parsed_output["selected_candidate_ids"] == ["e1"]
    assert result.traces[0].final_output["selected_candidate_ids"] == ["ev1"]


def test_proof_step_rejects_required_candidates_that_are_not_cited() -> None:
    with pytest.raises(ValueError, match="required_candidate_ids must be a subset"):
        ProofStep(
            step_id="step:bad",
            description="bad proof step",
            candidate_ids=["ev1"],
            required_candidate_ids=["ev2"],
            citations=[],
            rationale="required candidate is absent from candidate_ids",
        )


def test_proof_step_rejects_citation_candidates_that_are_not_in_step() -> None:
    with pytest.raises(ValueError, match="citations candidate_id must be a subset"):
        ProofStep(
            step_id="step:bad-citation",
            description="bad proof citation",
            candidate_ids=["ev1"],
            required_candidate_ids=[],
            citations=[
                ProofStepCitation(
                    candidate_id="ev2",
                    role="direct_answer",
                    required_for_final_support=False,
                    claim_supported="wrong citation",
                    rationale="citation points outside the proof step",
                )
            ],
            rationale="citation candidate is absent from candidate_ids",
        )


def test_proof_step_rejects_candidates_without_citation_roles() -> None:
    with pytest.raises(ValueError, match="citations must role-label"):
        ProofStep(
            step_id="step:missing-citations",
            description="proof step without citation roles",
            candidate_ids=["ev1"],
            required_candidate_ids=["ev1"],
            citations=[],
            rationale="invalid structured output",
        )


def test_proof_step_allows_proof_required_context_that_is_not_final_support() -> None:
    step = ProofStep(
        step_id="step:proof-required-context",
        description="Proof step needs context that should not be a final citation.",
        candidate_ids=["ev1"],
        required_candidate_ids=["ev1"],
        citations=[
            ProofStepCitation(
                candidate_id="ev1",
                role="background_context",
                required_for_final_support=False,
                claim_supported="context necessary for proof interpretation",
                rationale="required for proof but not final citation support",
            )
        ],
        rationale="proof required context is distinct from final support",
    )

    assert step.required_candidate_ids == ["ev1"]
    assert step.citations[0].required_for_final_support is False


def test_grounded_answer_pipeline_uses_prompt_local_ids_for_long_candidate_ids() -> None:
    original_id = "hotpotqa:example-with-long-id:paragraph-0001:sentence-0001"
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_LongIdEvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_long_id_context(), request_id_prefix="req:grounding:long-ids")

    assert result.success is True
    assert result.selected_candidate_ids == [original_id]
    assert result.proof_citation_candidate_ids == [original_id]
    assert result.answer_citation_candidate_ids == [original_id]
    assert result.verified_citation_candidate_ids == [original_id]
    assert result.citation_candidate_ids == [original_id]
    assert result.traces[0].parsed_output["selected_candidate_ids"] == ["e1"]
    assert result.traces[0].final_output["selected_candidate_ids"] == [original_id]


def test_grounded_answer_pipeline_flattens_proof_steps_and_repairs_citations() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_RepairingVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:repair")

    assert result.success is True
    assert result.selected_candidate_ids == ["ev1", "ev2"]
    assert result.proof_citation_candidate_ids == ["ev1", "ev2"]
    assert result.answer_citation_candidate_ids == ["ev1"]
    assert result.verified_citation_candidate_ids == ["ev1", "ev2"]
    assert result.citation_candidate_ids == ["ev1", "ev2"]


def test_grounded_answer_pipeline_reconciles_and_trims_proof_only_noise() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:minimal-final")

    assert result.success is True
    assert result.proof_citation_candidate_ids == ["ev1", "ev2"]
    assert result.answer_citation_candidate_ids == ["ev1"]
    assert result.verified_citation_candidate_ids == ["ev1"]
    assert result.citation_candidate_ids == ["ev1"]
    assert result.provenance_reconciliation.final_citation_candidate_ids == ["ev1"]
    assert result.provenance_reconciliation.dropped_citation_candidate_ids == ["ev2"]
    assert result.provenance_reconciliation.covered_proof_step_ids == ["step:1"]
    assert result.provenance_reconciliation.uncovered_proof_step_ids == []


def test_grounded_answer_pipeline_does_not_drop_answer_citations_when_verifier_under_cites() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerSecondEvidenceAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:additive-repair")

    assert result.success is True
    assert result.answer_citation_candidate_ids == ["ev2"]
    assert result.verified_citation_candidate_ids == ["ev1"]
    assert result.proof_citation_candidate_ids == ["ev1", "ev2"]
    assert result.citation_candidate_ids == ["ev1", "ev2"]


def test_grounded_answer_pipeline_keeps_answer_citations_when_verifier_returns_empty_citations() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerSecondEvidenceAdapter(),
        verifier=_EmptyCitationVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:empty-verifier-citations")

    assert result.success is True
    assert result.answer_citation_candidate_ids == ["ev2"]
    assert result.verified_citation_candidate_ids == []
    assert result.proof_citation_candidate_ids == ["ev1", "ev2"]
    assert result.citation_candidate_ids == ["ev2"]
    assert result.provenance_reconciliation.strategy == "answer_role_proof_no_verifier_citations"


def test_provenance_reconciliation_preserves_steps_without_stronger_citations() -> None:
    selection = EvidenceSelectionDecision(
        selected_candidate_ids=["ev3", "ev1", "ev2"],
        excluded_candidate_ids=[],
        ranking=["ev3", "ev1", "ev2"],
        proof_steps=[
            _proof_step(
                step_id="step:bridge",
                description="Bridge evidence that answer/verifier did not cite.",
                candidate_ids=["ev2", "ev1", "ev2"],
                rationale="Both bridge candidates are retained because no stronger citation covers the step.",
            ),
            _proof_step(
                step_id="step:answer",
                description="Direct answer evidence.",
                candidate_ids=["ev3"],
                rationale="The answer candidate is cited by answerer and verifier.",
            ),
        ],
        confidence=0.9,
        rationale="multi-step proof",
    )

    reconciliation = reconcile_provenance(
        selection=selection,
        selected_evidence=_three_evidence(),
        answer_citation_ids=["ev3", "ev3"],
        verified_citation_ids=["ev3"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert reconciliation.final_citation_candidate_ids == ["ev1", "ev2", "ev3"]
    assert reconciliation.added_citation_candidate_ids == ["ev1", "ev2"]
    assert reconciliation.dropped_citation_candidate_ids == []
    assert reconciliation.covered_proof_step_ids == ["step:bridge", "step:answer"]
    assert reconciliation.uncovered_proof_step_ids == []


def test_provenance_reconciliation_preserves_required_proof_citations_when_verifier_under_cites() -> None:
    selection = EvidenceSelectionDecision(
        selected_candidate_ids=["ev1", "ev2"],
        excluded_candidate_ids=[],
        ranking=["ev1", "ev2"],
        proof_steps=[
            _proof_step(
                step_id="step:required-bridge",
                description="Both proof candidates are required.",
                candidate_ids=["ev1", "ev2"],
                rationale="The answer needs both candidates.",
            )
        ],
        confidence=0.9,
        rationale="required proof citations",
    )

    reconciliation = reconcile_provenance(
        selection=selection,
        selected_evidence=_three_evidence()[:2],
        answer_citation_ids=["ev1"],
        verified_citation_ids=["ev1"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert reconciliation.final_citation_candidate_ids == ["ev1", "ev2"]
    assert reconciliation.added_citation_candidate_ids == ["ev2"]
    assert reconciliation.dropped_citation_candidate_ids == []


def test_provenance_reconciliation_drops_background_context_proof_noise() -> None:
    selection = EvidenceSelectionDecision(
        selected_candidate_ids=["ev1", "ev2", "ev3"],
        excluded_candidate_ids=[],
        ranking=["ev1", "ev2", "ev3"],
        proof_steps=[
            ProofStep(
                step_id="step:answer",
                description="Direct answer with background context.",
                candidate_ids=["ev1", "ev2", "ev3"],
                required_candidate_ids=["ev1"],
                citations=[
                    ProofStepCitation(
                        candidate_id="ev1",
                        role="direct_answer",
                        required_for_final_support=True,
                        claim_supported="Ada Lovelace wrote notes.",
                        rationale="direct answer support",
                    ),
                    ProofStepCitation(
                        candidate_id="ev2",
                        role="background_context",
                        required_for_final_support=False,
                        claim_supported="Analytical Engine context.",
                        rationale="helpful but not final support",
                    ),
                    ProofStepCitation(
                        candidate_id="ev3",
                        role="background_context",
                        required_for_final_support=False,
                        claim_supported="extra context.",
                        rationale="helpful but not final support",
                    ),
                ],
                rationale="answer proof with noisy context",
            )
        ],
        confidence=0.9,
        rationale="role-aware proof",
    )

    reconciliation = reconcile_provenance(
        selection=selection,
        selected_evidence=_three_evidence(),
        answer_citation_ids=["ev1"],
        verified_citation_ids=["ev1"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert reconciliation.final_citation_candidate_ids == ["ev1"]
    assert reconciliation.dropped_citation_candidate_ids == ["ev2", "ev3"]
    assert reconciliation.covered_proof_step_ids == ["step:answer"]


def test_answer_finalization_accepts_supported_canonical_correction() -> None:
    decision = finalize_answer(
        raw_answer="Helsinki",
        verification=AnswerVerificationDecision(
            entailed=True,
            corrected_answer="Helsinki, Finland",
            required_candidate_ids=["ev1"],
            missing_candidate_ids=[],
            confidence=0.9,
            rationale="full location is supported",
        ),
        selected_evidence=[EvidenceCandidate(candidate_id="ev1", text="The event was held in Helsinki, Finland.")],
        final_citation_ids=["ev1"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert decision.accepted is True
    assert decision.answer_changed is True
    assert decision.raw_answer == "Helsinki"
    assert decision.final_answer == "Helsinki, Finland"
    assert decision.supporting_candidate_ids == ["ev1"]


def test_answer_finalization_rejects_title_only_correction() -> None:
    decision = finalize_answer(
        raw_answer="Helsinki",
        verification=AnswerVerificationDecision(
            entailed=True,
            corrected_answer="Helsinki, Finland",
            required_candidate_ids=["ev1"],
            missing_candidate_ids=[],
            confidence=0.9,
            rationale="title has full location",
        ),
        selected_evidence=[EvidenceCandidate(candidate_id="ev1", title="Helsinki, Finland", text="The event was held there.")],
        final_citation_ids=["ev1"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert decision.accepted is False
    assert decision.final_answer == "Helsinki"
    assert decision.rejected_reason == "correction_not_supported_by_selected_evidence"


def test_answer_finalization_rejects_unsupported_extra_tokens() -> None:
    decision = finalize_answer(
        raw_answer="eBay",
        verification=AnswerVerificationDecision(
            entailed=True,
            corrected_answer="eBay Inc. marketplace leader",
            required_candidate_ids=["ev1"],
            missing_candidate_ids=[],
            confidence=0.9,
            rationale="too broad",
        ),
        selected_evidence=[EvidenceCandidate(candidate_id="ev1", text="The auction was operated by eBay Inc.")],
        final_citation_ids=["ev1"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert decision.accepted is False
    assert decision.final_answer == "eBay"
    assert decision.rejected_reason == "correction_not_supported_by_selected_evidence"


def test_answer_finalization_rejects_non_entailed_correction() -> None:
    decision = finalize_answer(
        raw_answer="Ada Lovelace",
        verification=AnswerVerificationDecision(
            entailed=False,
            corrected_answer="Charles Babbage",
            required_candidate_ids=["ev1"],
            missing_candidate_ids=[],
            confidence=0.9,
            rationale="not entailed",
            failure_mode="not_entailed",
        ),
        selected_evidence=[EvidenceCandidate(candidate_id="ev1", text="Charles Babbage designed the engine.")],
        final_citation_ids=["ev1"],
        verified=False,
        verification_repair_allowed=True,
    )

    assert decision.accepted is False
    assert decision.final_answer == "Ada Lovelace"
    assert decision.rejected_reason == "answer_not_verified"


def test_answer_finalization_rejects_verbose_binary_correction() -> None:
    decision = finalize_answer(
        raw_answer="yes",
        verification=AnswerVerificationDecision(
            entailed=True,
            corrected_answer="Yes, both are supported.",
            required_candidate_ids=["ev1"],
            missing_candidate_ids=[],
            confidence=0.9,
            rationale="verbose binary answer",
        ),
        selected_evidence=[EvidenceCandidate(candidate_id="ev1", text="Both are supported by the evidence.")],
        final_citation_ids=["ev1"],
        verified=True,
        verification_repair_allowed=True,
    )

    assert decision.accepted is False
    assert decision.final_answer == "yes"
    assert decision.rejected_reason == "binary_correction_not_exact"


def test_grounded_answer_pipeline_rejects_invalid_verifier_repair_ids() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_InvalidCitationVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:invalid-repair")

    assert result.success is False
    assert result.fallback_used is True
    assert result.answer_citation_candidate_ids == ["ev1"]
    assert result.citation_candidate_ids == ["ev1"]
    assert result.verified_citation_candidate_ids == []
    assert "llm_decision_validation_failed" in (result.failure_mode or "")


def test_grounded_answer_pipeline_does_not_repair_non_entailed_answers() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_NonEntailedVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:not-entailed")

    assert result.success is False
    assert result.verified is False
    assert result.answer == "Ada Lovelace"
    assert result.answer_citation_candidate_ids == ["ev1"]
    assert result.verified_citation_candidate_ids == []
    assert result.citation_candidate_ids == ["ev1"]


def test_grounded_answer_pipeline_rejects_uncovered_question_constraints() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_EvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_UncoveredConstraintVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:uncovered-constraint")

    assert result.success is False
    assert result.verified is False
    assert result.answer_verification.entailed is False
    assert result.answer_verification.question_constraints[0].constraint_id == "constraint:bridge_entity"
    assert "question_constraints_uncovered:constraint:bridge_entity" in (result.failure_mode or "")


def test_grounded_answer_pipeline_rejects_missing_question_constraint_coverage() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_EvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_MissingConstraintsVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:missing-constraints")

    assert result.success is False
    assert result.verified is False
    assert result.answer_verification.entailed is False
    assert result.answer_verification.question_constraints == []
    assert "question_constraints_missing" in (result.failure_mode or "")


def test_grounded_answer_pipeline_rejects_better_alternative_answers() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_AnswerAdapter(),
        verifier=_BetterAlternativeVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:better-alternative")

    assert result.success is False
    assert result.verified is False
    assert result.answer_verification.alternative_answers[0].better_than_proposed_answer is True
    assert "better_alternative_answer" in (result.failure_mode or "")


def test_grounded_answer_pipeline_rejects_selected_candidate_missing_requirements() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_MissingRequirementAnswerAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:missing-answer-requirement")

    assert result.success is False
    assert result.verified is False
    assert result.answer_verification.entailed is False
    assert "selected_candidate_missing_requirements:r2" in (result.failure_mode or "")


def test_grounded_answer_pipeline_rejects_weaker_selected_candidate() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_BetterCoverageAnswerAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:better-candidate-coverage")

    assert result.success is False
    assert result.verified is False
    assert result.answer_verification.entailed is False
    assert "better_candidate_requirement_coverage" in (result.failure_mode or "")


def test_grounded_answer_pipeline_accepts_guarded_better_alternative_correction() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_TwoEvidenceAdapter(),
        answer_generator=_GuardedCorrectionAnswerAdapter(),
        verifier=_GuardedCorrectionVerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:guarded-correction")

    assert result.success is False
    assert result.verified is False
    assert result.answer == "Charles Babbage"
    assert result.answer_finalization.accepted is True
    assert result.answer_finalization.answer_changed is True
    assert result.answer_finalization.strategy == "guarded_better_alternative_correction"
    assert result.answer_finalization.supporting_candidate_ids == ["ev2"]


def test_grounded_answer_pipeline_rejects_invalid_answer_span_candidate_ids() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_EvidenceAdapter(),
        answer_generator=_InvalidAnswerSpanAdapter(),
        verifier=_VerificationAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:invalid-answer-span")

    assert result.success is False
    assert result.fallback_used is True
    assert "llm_decision_validation_failed" in (result.failure_mode or "")


def test_grounded_answer_pipeline_llm_failure_falls_back_traceably() -> None:
    result = GroundedAnswerPipeline(
        mode=LLMDecisionMode.LLM,
        evidence_selector=_InvalidAdapter(),
        answer_generator=_InvalidAdapter(),
        verifier=_InvalidAdapter(),
    ).run(_context(), request_id_prefix="req:grounding:invalid")

    assert result.success is False
    assert result.fallback_used is True
    assert "llm_decision_failed" in (result.failure_mode or "")
    assert len(result.traces) == 3
    assert all(trace.fallback_used is True for trace in result.traces)
