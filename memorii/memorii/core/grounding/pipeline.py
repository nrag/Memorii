"""Generic grounded answer pipeline."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from memorii.core.grounding.models import (
    AnswerFinalizationDecision,
    AnswerRequirement,
    AnswerVerificationContext,
    AnswerVerificationDecision,
    CandidateAnswerConsidered,
    CandidateRequirementCoverage,
    EvidenceCandidate,
    EvidenceSelectionContext,
    EvidenceSelectionDecision,
    GroundedAnswerContext,
    GroundedAnswerDecision,
    GroundedAnswerPipelineResult,
    ProofStepCitation,
    ProvenanceReconciliationDecision,
    QuestionConstraintCoverage,
)
from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


class EvidenceSelectionAdapter(Protocol):
    def decide(
        self,
        context: EvidenceSelectionContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult: ...


class GroundedAnswerAdapter(Protocol):
    def decide(
        self,
        context: GroundedAnswerContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult: ...


class AnswerVerificationAdapter(Protocol):
    def decide(
        self,
        context: AnswerVerificationContext,
        *,
        request_id: str,
        metadata: dict[str, object] | None = None,
    ) -> LLMDecisionResult: ...


DecisionModel = TypeVar("DecisionModel", bound=BaseModel)

_FINAL_SUPPORT_PROOF_ROLES = {
    "direct_answer",
    "bridge",
    "entity_link",
    "comparison_operand",
    "temporal_scope",
    "constraint_support",
    "disambiguation",
}


@dataclass(frozen=True)
class _CandidateIdAliases:
    original_by_local: dict[str, str]
    local_by_original: dict[str, str]

    @classmethod
    def from_candidates(cls, candidates: list[EvidenceCandidate]) -> _CandidateIdAliases:
        original_by_local = {f"e{index}": candidate.candidate_id for index, candidate in enumerate(candidates, start=1)}
        return cls(
            original_by_local=original_by_local,
            local_by_original={original: local for local, original in original_by_local.items()},
        )

    def to_original_id(self, candidate_id: str) -> str:
        return self.original_by_local.get(candidate_id, candidate_id)

    def to_local_id(self, candidate_id: str) -> str:
        return self.local_by_original.get(candidate_id, candidate_id)

    def to_original_ids(self, candidate_ids: list[str]) -> list[str]:
        return [self.to_original_id(candidate_id) for candidate_id in candidate_ids]

    def to_local_ids(self, candidate_ids: list[str]) -> list[str]:
        return [self.to_local_id(candidate_id) for candidate_id in candidate_ids]

    def trace_metadata(self) -> dict[str, str]:
        return dict(self.original_by_local)


class GroundedAnswerPipeline:
    def __init__(
        self,
        *,
        mode: LLMDecisionMode | str,
        evidence_selector: EvidenceSelectionAdapter | None = None,
        answer_generator: GroundedAnswerAdapter | None = None,
        verifier: AnswerVerificationAdapter | None = None,
    ) -> None:
        self._mode = LLMDecisionMode(mode)
        self._evidence_selector = evidence_selector
        self._answer_generator = answer_generator
        self._verifier = verifier

    def run(
        self,
        context: EvidenceSelectionContext,
        *,
        request_id_prefix: str,
        metadata: dict[str, object] | None = None,
    ) -> GroundedAnswerPipelineResult:
        traces: list[LLMDecisionTrace] = []
        fallback_used = False
        failure_modes: list[str] = []

        rule_selection = rule_evidence_selection(context)
        selection = rule_selection
        if self._mode in {LLMDecisionMode.LLM, LLMDecisionMode.HYBRID} and self._evidence_selector is not None:
            evidence_aliases = _CandidateIdAliases.from_candidates(context.candidates)
            local_context = _localize_evidence_selection_context(context, evidence_aliases)
            selection, trace, success, failure_mode = _run_llm_decision(
                result=self._evidence_selector.decide(
                    local_context,
                    request_id=f"{request_id_prefix}:evidence_selection",
                    metadata=_step_metadata(metadata, LLMDecisionPoint.EVIDENCE_SELECTION, aliases=evidence_aliases),
                ),
                mode=self._mode,
                decision_point=LLMDecisionPoint.EVIDENCE_SELECTION,
                decision_model=EvidenceSelectionDecision,
                rule_decision=rule_selection,
                validate=lambda decision: _validate_evidence_selection_ids(decision, _candidate_ids(context.candidates)),
                transform=lambda decision: _map_evidence_selection_decision_to_original(decision, evidence_aliases),
            )
            selection = _normalize_evidence_selection(selection)
            traces.append(trace)
            if not success:
                fallback_used = True
                failure_modes.append(failure_mode or "evidence_selection_failed")
        else:
            if self._mode in {LLMDecisionMode.LLM, LLMDecisionMode.HYBRID}:
                fallback_used = True
                failure_modes.append("evidence_selection_adapter_missing")
            traces.append(_rule_trace(LLMDecisionPoint.EVIDENCE_SELECTION, self._mode, context.model_dump(mode="json"), selection))

        selected_evidence = _selected_candidates(context.candidates, selection.selected_candidate_ids)
        answer_context = GroundedAnswerContext(
            query=context.query,
            evidence=selected_evidence,
            answer_format=context.answer_format,
            metadata=context.metadata,
        )
        rule_answer = rule_grounded_answer(answer_context)
        answer = rule_answer
        if self._mode in {LLMDecisionMode.LLM, LLMDecisionMode.HYBRID} and self._answer_generator is not None:
            answer_aliases = _CandidateIdAliases.from_candidates(selected_evidence)
            local_answer_context = _localize_grounded_answer_context(answer_context, answer_aliases)
            answer, trace, success, failure_mode = _run_llm_decision(
                result=self._answer_generator.decide(
                    local_answer_context,
                    request_id=f"{request_id_prefix}:grounded_answer",
                    metadata=_step_metadata(metadata, LLMDecisionPoint.GROUNDED_ANSWER, aliases=answer_aliases),
                ),
                mode=self._mode,
                decision_point=LLMDecisionPoint.GROUNDED_ANSWER,
                decision_model=GroundedAnswerDecision,
                rule_decision=rule_answer,
                validate=lambda decision: _validate_grounded_answer_ids(decision, _candidate_ids(selected_evidence)),
                transform=lambda decision: _map_grounded_answer_decision_to_original(decision, answer_aliases),
            )
            traces.append(trace)
            if not success:
                fallback_used = True
                failure_modes.append(failure_mode or "grounded_answer_failed")
        else:
            if self._mode in {LLMDecisionMode.LLM, LLMDecisionMode.HYBRID}:
                fallback_used = True
                failure_modes.append("grounded_answer_adapter_missing")
            traces.append(_rule_trace(LLMDecisionPoint.GROUNDED_ANSWER, self._mode, answer_context.model_dump(mode="json"), answer))

        verification_context = AnswerVerificationContext(
            query=context.query,
            answer=answer.answer,
            evidence=selected_evidence,
            citation_candidate_ids=answer.citation_candidate_ids,
            answer_requirements=answer.answer_requirements,
            candidate_answers_considered=answer.candidate_answers_considered,
            metadata=context.metadata,
        )
        rule_verification = rule_answer_verification(verification_context)
        verification = rule_verification
        verification_repair_allowed = self._mode == LLMDecisionMode.RULE
        if self._mode in {LLMDecisionMode.LLM, LLMDecisionMode.HYBRID} and self._verifier is not None:
            verification_aliases = _CandidateIdAliases.from_candidates(selected_evidence)
            local_verification_context = _localize_answer_verification_context(verification_context, verification_aliases)
            verification, trace, success, failure_mode = _run_llm_decision(
                result=self._verifier.decide(
                    local_verification_context,
                    request_id=f"{request_id_prefix}:answer_verification",
                    metadata=_step_metadata(metadata, LLMDecisionPoint.ANSWER_VERIFICATION, aliases=verification_aliases),
                ),
                mode=self._mode,
                decision_point=LLMDecisionPoint.ANSWER_VERIFICATION,
                decision_model=AnswerVerificationDecision,
                rule_decision=rule_verification,
                validate=lambda decision: _validate_answer_verification_ids(decision, _candidate_ids(selected_evidence)),
                transform=lambda decision: _map_answer_verification_decision_to_original(decision, verification_aliases),
            )
            traces.append(trace)
            if not success:
                verification_repair_allowed = False
                fallback_used = True
                failure_modes.append(failure_mode or "answer_verification_failed")
            else:
                verification_repair_allowed = True
        else:
            if self._mode in {LLMDecisionMode.LLM, LLMDecisionMode.HYBRID}:
                verification_repair_allowed = False
                fallback_used = True
                failure_modes.append("answer_verification_adapter_missing")
            traces.append(
                _rule_trace(
                    LLMDecisionPoint.ANSWER_VERIFICATION,
                    self._mode,
                    verification_context.model_dump(mode="json"),
                    verification,
                )
            )

        verification = _apply_answer_verification_gates(
            verification,
            answer_requirements=answer.answer_requirements,
            candidate_answers_considered=answer.candidate_answers_considered,
        )
        verified = bool(verification.entailed)
        if not verified:
            failure_modes.append(verification.failure_mode or "answer_not_entailed")
        answer_citation_ids = list(answer.citation_candidate_ids)
        answer_requirements = list(answer.answer_requirements)
        verified_citation_ids = _valid_verifier_citations(
            verification=verification,
            selected_evidence=selected_evidence,
        )
        proof_citation_ids = _ordered_unique(_proof_step_candidate_ids(selection))
        required_proof_citation_ids = _ordered_unique(_proof_step_required_candidate_ids(selection))
        provenance_reconciliation = reconcile_provenance(
            selection=selection,
            selected_evidence=selected_evidence,
            answer_citation_ids=answer_citation_ids,
            verified_citation_ids=verified_citation_ids,
            verified=verified,
            verification_repair_allowed=verification_repair_allowed,
        )
        final_citation_ids = provenance_reconciliation.final_citation_candidate_ids
        answer_finalization = finalize_answer(
            raw_answer=answer.answer,
            verification=verification,
            selected_evidence=selected_evidence,
            final_citation_ids=final_citation_ids,
            verified=verified,
            verification_repair_allowed=verification_repair_allowed,
            candidate_answers_considered=answer.candidate_answers_considered,
            answer_requirements=answer_requirements,
        )
        success = verified and not (self._mode == LLMDecisionMode.LLM and fallback_used)
        return GroundedAnswerPipelineResult(
            answer=answer_finalization.final_answer,
            selected_candidate_ids=list(selection.selected_candidate_ids),
            proof_citation_candidate_ids=proof_citation_ids,
            required_proof_citation_candidate_ids=required_proof_citation_ids,
            answer_citation_candidate_ids=answer_citation_ids,
            verified_citation_candidate_ids=verified_citation_ids if verified and verification_repair_allowed else [],
            citation_candidate_ids=final_citation_ids,
            verified=verified,
            confidence=min(selection.confidence, answer.confidence, verification.confidence),
            fallback_used=fallback_used,
            success=success,
            failure_mode=",".join(_ordered_unique(failure_modes)) or None,
            rationale=" | ".join([selection.rationale, answer.rationale, verification.rationale]),
            evidence_selection=selection,
            grounded_answer=answer,
            answer_verification=verification,
            provenance_reconciliation=provenance_reconciliation,
            answer_finalization=answer_finalization,
            traces=traces,
        )


def rule_evidence_selection(context: EvidenceSelectionContext) -> EvidenceSelectionDecision:
    ranked = sorted(
        context.candidates,
        key=lambda item: (_lexical_overlap(context.query, f"{item.title or ''} {item.text}"), item.candidate_id),
        reverse=True,
    )
    selected = [candidate.candidate_id for candidate in ranked[:2]]
    ranking = [candidate.candidate_id for candidate in ranked]
    return EvidenceSelectionDecision(
        selected_candidate_ids=selected,
        excluded_candidate_ids=ranking[2:],
        ranking=ranking,
        proof_steps=[
            _proof_step(
                step_id="step:lexical_overlap",
                description="Highest lexical-overlap evidence selected by the rule provider.",
                candidate_ids=selected,
                required_candidate_ids=selected,
                rationale="Rule evidence selector does not build semantic proof steps.",
            )
        ] if selected else [],
        confidence=0.35,
        rationale="rule evidence selector uses shallow lexical overlap",
        failure_mode="rule_limit",
        requires_judge_review=True,
    )


def rule_grounded_answer(context: GroundedAnswerContext) -> GroundedAnswerDecision:
    if not context.evidence:
        return GroundedAnswerDecision(
            answer="noanswer",
            citation_candidate_ids=[],
            answer_requirements=[],
            candidate_answers_considered=[],
            answer_type="noanswer",
            answer_span_candidate_id=None,
            answer_span_text=None,
            confidence=0.2,
            rationale="rule answer fallback found no selected evidence",
            failure_mode="insufficient_evidence",
            requires_judge_review=True,
        )
    first = context.evidence[0]
    words = first.text.replace(".", "").split()
    answer = " ".join(words[: min(5, len(words))]) or "noanswer"
    return GroundedAnswerDecision(
        answer=answer,
        citation_candidate_ids=[first.candidate_id],
        answer_requirements=[
            AnswerRequirement(
                requirement_id="requirement:answer_tokens_in_evidence",
                description="The answer must be supported by selected evidence text.",
                requirement_type="direct_answer",
                candidate_ids=[first.candidate_id],
                rationale="Rule answer fallback uses the highest-ranked evidence as direct support.",
            )
        ],
        candidate_answers_considered=[
            CandidateAnswerConsidered(
                answer=answer,
                candidate_ids=[first.candidate_id],
                selected=True,
                answer_type="short_span",
                requirement_coverage=[
                    CandidateRequirementCoverage(
                        requirement_id="requirement:answer_tokens_in_evidence",
                        satisfied=True,
                        candidate_ids=[first.candidate_id],
                        rationale="Rule answer fallback treats the extracted span as supported by the first evidence item.",
                    )
                ],
                satisfied_requirement_ids=["requirement:answer_tokens_in_evidence"],
                missing_requirement_ids=[],
                rationale="Rule answer fallback considered only the highest-ranked evidence span.",
            )
        ],
        answer_type="short_span",
        answer_span_candidate_id=first.candidate_id,
        answer_span_text=answer,
        confidence=0.35,
        rationale="rule answer fallback extracts a short span from the highest-ranked evidence",
        failure_mode="rule_limit",
        requires_judge_review=True,
    )


def rule_answer_verification(context: AnswerVerificationContext) -> AnswerVerificationDecision:
    evidence_text = " ".join(candidate.text for candidate in context.evidence)
    answer_tokens = _tokens(context.answer)
    evidence_tokens = _tokens(evidence_text)
    entailed = bool(answer_tokens) and answer_tokens.issubset(evidence_tokens)
    return AnswerVerificationDecision(
        entailed=entailed,
        corrected_answer=None,
        required_candidate_ids=list(context.citation_candidate_ids),
        missing_candidate_ids=[],
        question_constraints=[
            QuestionConstraintCoverage(
                constraint_id="constraint:answer_tokens_in_evidence",
                description="The answer tokens must be present in the selected evidence text.",
                satisfied=entailed,
                candidate_ids=list(context.citation_candidate_ids) if entailed else [],
                rationale="Rule verifier performs shallow token containment rather than semantic constraint checking.",
            )
        ],
        alternative_answers=[],
        confidence=0.35,
        rationale="rule verifier checks whether answer tokens are present in selected evidence",
        failure_mode=None if entailed else "not_entailed",
        requires_judge_review=not entailed,
    )


def fake_llm_result_for_evidence_selection(
    *,
    request: LLMStructuredRequest,
    decision: EvidenceSelectionDecision,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    return _fake_result(request=request, decision=decision, provider_name=provider_name)


def fake_llm_result_for_grounded_answer(
    *,
    request: LLMStructuredRequest,
    decision: GroundedAnswerDecision,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    return _fake_result(request=request, decision=decision, provider_name=provider_name)


def fake_llm_result_for_answer_verification(
    *,
    request: LLMStructuredRequest,
    decision: AnswerVerificationDecision,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    return _fake_result(request=request, decision=decision, provider_name=provider_name)


def _run_llm_decision(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    decision_point: LLMDecisionPoint,
    decision_model: type[DecisionModel],
    rule_decision: DecisionModel,
    validate: Callable[[DecisionModel], list[str]],
    transform: Callable[[DecisionModel], DecisionModel] | None = None,
) -> tuple[DecisionModel, LLMDecisionTrace, bool, str | None]:
    rule_output = rule_decision.model_dump(mode="json")
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=decision_point,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_decision, trace, False, "llm_decision_failed"
    try:
        decision = decision_model.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=decision_point,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_decision, trace, False, "llm_decision_validation_failed"
    final_decision = transform(decision) if transform is not None else decision
    validation_errors = validate(final_decision)
    if validation_errors:
        failed_result = result.model_copy(update={"failure_mode": ",".join(validation_errors)})
        trace = build_llm_decision_trace_from_result(
            decision_point=decision_point,
            mode=mode,
            result=failed_result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_decision, trace, False, "llm_decision_validation_failed"
    output = final_decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=decision_point,
        mode=mode,
        result=result,
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return final_decision, trace, True, None


def _rule_trace(
    decision_point: LLMDecisionPoint,
    mode: LLMDecisionMode,
    input_payload: dict[str, object],
    decision: BaseModel,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=decision_point,
        mode=mode,
        input_payload=input_payload,
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def _fake_result(
    *,
    request: LLMStructuredRequest,
    decision: BaseModel,
    provider_name: str,
) -> LLMDecisionResult:
    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        raw_text=json.dumps(output, sort_keys=True),
        parsed_json=output,
        valid_json=True,
        schema_valid=True,
    )
    return LLMDecisionResult(
        request=request,
        response=response,
        output=output,
        success=True,
        failure_mode=None,
    )


def _localize_evidence_selection_context(
    context: EvidenceSelectionContext,
    aliases: _CandidateIdAliases,
) -> EvidenceSelectionContext:
    return context.model_copy(
        update={
            "candidates": [_localize_candidate(candidate, aliases) for candidate in context.candidates],
        }
    )


def _localize_grounded_answer_context(
    context: GroundedAnswerContext,
    aliases: _CandidateIdAliases,
) -> GroundedAnswerContext:
    return context.model_copy(
        update={
            "evidence": [_localize_candidate(candidate, aliases) for candidate in context.evidence],
        }
    )


def _localize_answer_verification_context(
    context: AnswerVerificationContext,
    aliases: _CandidateIdAliases,
) -> AnswerVerificationContext:
    return context.model_copy(
        update={
            "evidence": [_localize_candidate(candidate, aliases) for candidate in context.evidence],
            "citation_candidate_ids": aliases.to_local_ids(context.citation_candidate_ids),
            "answer_requirements": [
                requirement.model_copy(update={"candidate_ids": aliases.to_local_ids(requirement.candidate_ids)})
                for requirement in context.answer_requirements
            ],
            "candidate_answers_considered": [
                _localize_candidate_answer(candidate_answer, aliases)
                for candidate_answer in context.candidate_answers_considered
            ],
        }
    )


def _localize_candidate(candidate: EvidenceCandidate, aliases: _CandidateIdAliases) -> EvidenceCandidate:
    return candidate.model_copy(
        update={
            "candidate_id": aliases.to_local_id(candidate.candidate_id),
            "source_id": aliases.to_local_id(candidate.source_id) if candidate.source_id is not None else None,
            "metadata": _replace_candidate_ids_in_metadata(candidate.metadata, aliases),
        }
    )


def _replace_candidate_ids_in_metadata(value: object, aliases: _CandidateIdAliases) -> object:
    if isinstance(value, str):
        return aliases.to_local_id(value)
    if isinstance(value, dict):
        return {key: _replace_candidate_ids_in_metadata(inner, aliases) for key, inner in value.items()}
    if isinstance(value, list):
        return [_replace_candidate_ids_in_metadata(inner, aliases) for inner in value]
    return value


def _map_evidence_selection_decision_to_original(
    decision: EvidenceSelectionDecision,
    aliases: _CandidateIdAliases,
) -> EvidenceSelectionDecision:
    return decision.model_copy(
        update={
            "selected_candidate_ids": aliases.to_original_ids(decision.selected_candidate_ids),
            "excluded_candidate_ids": aliases.to_original_ids(decision.excluded_candidate_ids),
            "ranking": aliases.to_original_ids(decision.ranking),
            "proof_steps": [
                step.model_copy(
                    update={
                        "candidate_ids": aliases.to_original_ids(step.candidate_ids),
                        "required_candidate_ids": aliases.to_original_ids(step.required_candidate_ids),
                        "citations": [
                            citation.model_copy(update={"candidate_id": aliases.to_original_id(citation.candidate_id)})
                            for citation in step.citations
                        ],
                    }
                )
                for step in decision.proof_steps
            ],
        }
    )


def _map_grounded_answer_decision_to_original(
    decision: GroundedAnswerDecision,
    aliases: _CandidateIdAliases,
) -> GroundedAnswerDecision:
    return decision.model_copy(
        update={
            "citation_candidate_ids": aliases.to_original_ids(decision.citation_candidate_ids),
            "answer_span_candidate_id": (
                aliases.to_original_id(decision.answer_span_candidate_id)
                if decision.answer_span_candidate_id is not None
                else None
            ),
            "candidate_answers_considered": [
                _map_candidate_answer_to_original(candidate_answer, aliases)
                for candidate_answer in decision.candidate_answers_considered
            ],
            "answer_requirements": [
                requirement.model_copy(update={"candidate_ids": aliases.to_original_ids(requirement.candidate_ids)})
                for requirement in decision.answer_requirements
            ],
        }
    )


def _map_answer_verification_decision_to_original(
    decision: AnswerVerificationDecision,
    aliases: _CandidateIdAliases,
) -> AnswerVerificationDecision:
    return decision.model_copy(
        update={
            "required_candidate_ids": aliases.to_original_ids(decision.required_candidate_ids),
            "missing_candidate_ids": aliases.to_original_ids(decision.missing_candidate_ids),
            "question_constraints": [
                constraint.model_copy(update={"candidate_ids": aliases.to_original_ids(constraint.candidate_ids)})
                for constraint in decision.question_constraints
            ],
            "alternative_answers": [
                alternative.model_copy(update={"candidate_ids": aliases.to_original_ids(alternative.candidate_ids)})
                for alternative in decision.alternative_answers
            ],
        }
    )


def _selected_candidates(candidates: list[EvidenceCandidate], selected_ids: list[str]) -> list[EvidenceCandidate]:
    by_id = {candidate.candidate_id: candidate for candidate in candidates}
    return [by_id[candidate_id] for candidate_id in selected_ids if candidate_id in by_id]


def _localize_candidate_answer(candidate_answer: CandidateAnswerConsidered, aliases: _CandidateIdAliases) -> CandidateAnswerConsidered:
    return candidate_answer.model_copy(
        update={
            "candidate_ids": aliases.to_local_ids(candidate_answer.candidate_ids),
            "requirement_coverage": [
                coverage.model_copy(update={"candidate_ids": aliases.to_local_ids(coverage.candidate_ids)})
                for coverage in candidate_answer.requirement_coverage
            ],
        }
    )


def _map_candidate_answer_to_original(candidate_answer: CandidateAnswerConsidered, aliases: _CandidateIdAliases) -> CandidateAnswerConsidered:
    return candidate_answer.model_copy(
        update={
            "candidate_ids": aliases.to_original_ids(candidate_answer.candidate_ids),
            "requirement_coverage": [
                coverage.model_copy(update={"candidate_ids": aliases.to_original_ids(coverage.candidate_ids)})
                for coverage in candidate_answer.requirement_coverage
            ],
        }
    )


def _candidate_ids(candidates: list[EvidenceCandidate]) -> set[str]:
    return {candidate.candidate_id for candidate in candidates}


def _validate_ids(ids: list[str], legal_ids: set[str]) -> list[str]:
    seen: set[str] = set()
    errors: list[str] = []
    for item_id in ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        if item_id not in legal_ids:
            errors.append(f"invalid_candidate_id:{item_id}")
    return errors


def _validate_evidence_selection_ids(decision: EvidenceSelectionDecision, legal_ids: set[str]) -> list[str]:
    errors = _validate_ids(
        [
            *decision.selected_candidate_ids,
            *decision.excluded_candidate_ids,
            *decision.ranking,
            *_proof_step_candidate_ids(decision),
            *_proof_step_required_candidate_ids(decision),
            *_proof_step_citation_candidate_ids(decision),
        ],
        legal_ids,
    )
    for step in decision.proof_steps:
        missing_required = [candidate_id for candidate_id in step.required_candidate_ids if candidate_id not in step.candidate_ids]
        errors.extend(f"required_candidate_not_in_step:{step.step_id}:{candidate_id}" for candidate_id in missing_required)
        missing_citation_ids = [citation.candidate_id for citation in step.citations if citation.candidate_id not in step.candidate_ids]
        errors.extend(f"citation_candidate_not_in_step:{step.step_id}:{candidate_id}" for candidate_id in missing_citation_ids)
        required_without_citation = [
            candidate_id
            for candidate_id in step.required_candidate_ids
            if not any(citation.candidate_id == candidate_id for citation in step.citations)
        ]
        errors.extend(
            f"required_candidate_missing_citation:{step.step_id}:{candidate_id}"
            for candidate_id in required_without_citation
        )
    return errors


def _validate_grounded_answer_ids(decision: GroundedAnswerDecision, legal_ids: set[str]) -> list[str]:
    ids = list(decision.citation_candidate_ids)
    if decision.answer_span_candidate_id is not None:
        ids.append(decision.answer_span_candidate_id)
    ids.extend(_candidate_answer_considered_candidate_ids(decision))
    ids.extend(candidate_id for requirement in decision.answer_requirements for candidate_id in requirement.candidate_ids)
    ids.extend(
        candidate_id
        for candidate_answer in decision.candidate_answers_considered
        for coverage in candidate_answer.requirement_coverage
        for candidate_id in coverage.candidate_ids
    )
    errors = _validate_ids(ids, legal_ids)
    selected = [candidate for candidate in decision.candidate_answers_considered if candidate.selected]
    if decision.answer != "noanswer" and len(selected) != 1:
        errors.append("selected_candidate_answer_invalid")
    if selected and _normalize_for_answer_compare(selected[0].answer) != _normalize_for_answer_compare(decision.answer):
        errors.append("selected_candidate_answer_mismatch")
    requirement_ids = {requirement.requirement_id for requirement in decision.answer_requirements}
    for candidate in decision.candidate_answers_considered:
        coverage_ids = {coverage.requirement_id for coverage in candidate.requirement_coverage}
        for requirement_id in [*candidate.satisfied_requirement_ids, *candidate.missing_requirement_ids, *coverage_ids]:
            if requirement_id not in requirement_ids:
                errors.append(f"invalid_requirement_id:{requirement_id}")
    return errors


def _validate_answer_verification_ids(decision: AnswerVerificationDecision, legal_ids: set[str]) -> list[str]:
    return _validate_ids(
        [
            *decision.required_candidate_ids,
            *decision.missing_candidate_ids,
            *_question_constraint_candidate_ids(decision),
            *_alternative_answer_candidate_ids(decision),
        ],
        legal_ids,
    )


def _proof_step(
    *,
    step_id: str,
    description: str,
    candidate_ids: list[str],
    required_candidate_ids: list[str] | None = None,
    rationale: str,
):
    from memorii.core.grounding.models import ProofStep

    required = list(candidate_ids if required_candidate_ids is None else required_candidate_ids)
    return ProofStep(
        step_id=step_id,
        description=description,
        candidate_ids=candidate_ids,
        required_candidate_ids=required,
        citations=[
            ProofStepCitation(
                candidate_id=candidate_id,
                role="constraint_support" if candidate_id in set(required) else "background_context",
                required_for_final_support=candidate_id in set(required),
                claim_supported=description,
                rationale=rationale,
            )
            for candidate_id in candidate_ids
        ],
        rationale=rationale,
    )


def _proof_step_candidate_ids(decision: EvidenceSelectionDecision) -> list[str]:
    return [candidate_id for step in decision.proof_steps for candidate_id in step.candidate_ids]


def _proof_step_required_candidate_ids(decision: EvidenceSelectionDecision) -> list[str]:
    return [candidate_id for step in decision.proof_steps for candidate_id in step.required_candidate_ids]


def _proof_step_citation_candidate_ids(decision: EvidenceSelectionDecision) -> list[str]:
    return [citation.candidate_id for step in decision.proof_steps for citation in step.citations]


def _role_eligible_required_proof_candidate_ids(decision: EvidenceSelectionDecision) -> list[str]:
    ids: list[str] = []
    for step in decision.proof_steps:
        for citation in step.citations:
            if citation.required_for_final_support and citation.role in _FINAL_SUPPORT_PROOF_ROLES:
                ids.append(citation.candidate_id)
    return ids


def _candidate_answer_considered_candidate_ids(decision: GroundedAnswerDecision) -> list[str]:
    return [candidate_id for candidate_answer in decision.candidate_answers_considered for candidate_id in candidate_answer.candidate_ids]


def _question_constraint_candidate_ids(decision: AnswerVerificationDecision) -> list[str]:
    return [candidate_id for constraint in decision.question_constraints for candidate_id in constraint.candidate_ids]


def _alternative_answer_candidate_ids(decision: AnswerVerificationDecision) -> list[str]:
    return [candidate_id for alternative in decision.alternative_answers for candidate_id in alternative.candidate_ids]


def _normalize_evidence_selection(decision: EvidenceSelectionDecision) -> EvidenceSelectionDecision:
    if not decision.proof_steps:
        return decision
    flattened = _ordered_unique(_proof_step_candidate_ids(decision))
    return decision.model_copy(update={"selected_candidate_ids": flattened})


def _valid_verifier_citations(
    *,
    verification: AnswerVerificationDecision,
    selected_evidence: list[EvidenceCandidate],
) -> list[str]:
    legal_ids = _candidate_ids(selected_evidence)
    return [
        candidate_id
        for candidate_id in _ordered_unique(list(verification.required_candidate_ids))
        if candidate_id in legal_ids
    ]


def _apply_answer_verification_gates(
    verification: AnswerVerificationDecision,
    *,
    answer_requirements: list[AnswerRequirement] | None = None,
    candidate_answers_considered: list[CandidateAnswerConsidered] | None = None,
) -> AnswerVerificationDecision:
    failure_reason = _answer_verification_failure_reason(
        verification,
        answer_requirements=answer_requirements or [],
        candidate_answers_considered=candidate_answers_considered or [],
    )
    if failure_reason is None:
        return verification
    return verification.model_copy(
        update={
            "entailed": False,
            "failure_mode": _append_failure_mode(verification.failure_mode, failure_reason),
            "requires_judge_review": True,
            "rationale": (
                f"{verification.rationale} Constraint coverage gate rejected verification: "
                f"{failure_reason}."
            ),
        }
    )


def _answer_verification_failure_reason(
    verification: AnswerVerificationDecision,
    *,
    answer_requirements: list[AnswerRequirement],
    candidate_answers_considered: list[CandidateAnswerConsidered],
) -> str | None:
    constraint_failure = _question_constraint_failure_reason(verification)
    if constraint_failure is not None:
        return constraint_failure
    candidate_failure = _candidate_answer_adjudication_failure_reason(
        candidate_answers_considered=candidate_answers_considered,
        answer_requirements=answer_requirements,
    )
    if candidate_failure is not None:
        return candidate_failure
    return _better_alternative_failure_reason(verification)


def _question_constraint_failure_reason(verification: AnswerVerificationDecision) -> str | None:
    if not verification.entailed:
        return None
    if not verification.question_constraints:
        return "question_constraints_missing"
    uncovered = [constraint.constraint_id for constraint in verification.question_constraints if not constraint.satisfied]
    if uncovered:
        return "question_constraints_uncovered:" + ",".join(uncovered)
    unsupported = [
        constraint.constraint_id
        for constraint in verification.question_constraints
        if constraint.satisfied and not constraint.candidate_ids
    ]
    if unsupported:
        return "question_constraints_missing_evidence:" + ",".join(unsupported)
    return None


def _better_alternative_failure_reason(verification: AnswerVerificationDecision) -> str | None:
    if not verification.entailed:
        return None
    better = [alternative.answer for alternative in verification.alternative_answers if alternative.better_than_proposed_answer]
    if not better:
        return None
    return "better_alternative_answer"


def _candidate_answer_adjudication_failure_reason(
    *,
    candidate_answers_considered: list[CandidateAnswerConsidered],
    answer_requirements: list[AnswerRequirement],
) -> str | None:
    if not answer_requirements:
        return None
    selected = [candidate for candidate in candidate_answers_considered if candidate.selected]
    if len(selected) != 1:
        return "selected_candidate_answer_missing"
    selected_candidate = selected[0]
    if selected_candidate.missing_requirement_ids:
        return "selected_candidate_missing_requirements:" + ",".join(selected_candidate.missing_requirement_ids)
    selected_score = _candidate_requirement_score(selected_candidate)
    for candidate in candidate_answers_considered:
        if candidate.selected:
            continue
        if candidate.missing_requirement_ids:
            continue
        if _candidate_requirement_score(candidate) > selected_score:
            return "better_candidate_requirement_coverage"
    return None


def _candidate_requirement_score(candidate: CandidateAnswerConsidered) -> int:
    if candidate.satisfied_requirement_ids:
        return len(set(candidate.satisfied_requirement_ids))
    return sum(1 for coverage in candidate.requirement_coverage if coverage.satisfied)


def _append_failure_mode(existing: str | None, failure_mode: str) -> str:
    if not existing:
        return failure_mode
    return ",".join(_ordered_unique([*existing.split(","), failure_mode]))


def reconcile_provenance(
    *,
    selection: EvidenceSelectionDecision,
    selected_evidence: list[EvidenceCandidate],
    answer_citation_ids: list[str],
    verified_citation_ids: list[str],
    verified: bool,
    verification_repair_allowed: bool,
) -> ProvenanceReconciliationDecision:
    legal_ids = _candidate_ids(selected_evidence)
    selected_order = [candidate.candidate_id for candidate in selected_evidence]
    answer_ids = _ordered_legal_unique(answer_citation_ids, legal_ids)
    verifier_ids = _ordered_legal_unique(verified_citation_ids, legal_ids)
    proof_ids = _ordered_legal_unique(_proof_step_candidate_ids(selection), legal_ids)
    required_proof_ids = _ordered_legal_unique(_proof_step_required_candidate_ids(selection), legal_ids)
    role_eligible_required_proof_ids = _ordered_legal_unique(_role_eligible_required_proof_candidate_ids(selection), legal_ids)
    all_input_ids = _ordered_unique([*proof_ids, *required_proof_ids, *answer_ids, *verifier_ids])

    if not verified:
        return ProvenanceReconciliationDecision(
            final_citation_candidate_ids=answer_ids,
            dropped_citation_candidate_ids=[candidate_id for candidate_id in all_input_ids if candidate_id not in set(answer_ids)],
            added_citation_candidate_ids=[],
            covered_proof_step_ids=[],
            uncovered_proof_step_ids=[step.step_id for step in selection.proof_steps],
            strategy="answer_citations_unverified",
            rationale="Answer was not verified, so reconciliation kept answerer citations only.",
        )
    if not verification_repair_allowed:
        return ProvenanceReconciliationDecision(
            final_citation_candidate_ids=answer_ids,
            dropped_citation_candidate_ids=[candidate_id for candidate_id in all_input_ids if candidate_id not in set(answer_ids)],
            added_citation_candidate_ids=[],
            covered_proof_step_ids=[],
            uncovered_proof_step_ids=[step.step_id for step in selection.proof_steps],
            strategy="answer_citations_verifier_unavailable",
            rationale="Verifier repair was unavailable or invalid, so reconciliation kept answerer citations only.",
        )
    if not verifier_ids:
        final_ids = _ordered_unique([*answer_ids, *role_eligible_required_proof_ids])
        final_set = set(final_ids)
        answer_set = set(answer_ids)
        return ProvenanceReconciliationDecision(
            final_citation_candidate_ids=final_ids,
            dropped_citation_candidate_ids=[candidate_id for candidate_id in all_input_ids if candidate_id not in final_set],
            added_citation_candidate_ids=[candidate_id for candidate_id in final_ids if candidate_id not in answer_set],
            covered_proof_step_ids=[
                step.step_id
                for step in selection.proof_steps
                if _step_has_final_support_citation(step, set(final_ids), legal_ids)
            ],
            uncovered_proof_step_ids=[
                step.step_id
                for step in selection.proof_steps
                if not _step_has_final_support_citation(step, set(final_ids), legal_ids)
            ],
            strategy="answer_role_proof_no_verifier_citations",
            rationale="Verifier returned no usable citations, so reconciliation kept answerer citations and role-eligible proof support.",
        )

    strong_ids = set(role_eligible_required_proof_ids) | set(answer_ids) | set(verifier_ids)
    selected_index = {candidate_id: index for index, candidate_id in enumerate(selected_order)}
    covered_step_ids: list[str] = []
    uncovered_step_ids: list[str] = []
    final_by_step: list[str] = []
    proof_step_ids: set[str] = set()

    for step in selection.proof_steps:
        step_ids = _ordered_legal_unique(step.candidate_ids, legal_ids)
        proof_step_ids.update(step_ids)
        if not step_ids:
            uncovered_step_ids.append(step.step_id)
            continue
        ordered_step_ids = sorted(step_ids, key=lambda candidate_id: selected_index.get(candidate_id, len(selected_order)))
        required_step_ids = [candidate_id for candidate_id in ordered_step_ids if candidate_id in set(role_eligible_required_proof_ids)]
        stronger_step_ids = [candidate_id for candidate_id in ordered_step_ids if candidate_id in strong_ids]
        if required_step_ids:
            final_by_step.extend(required_step_ids)
            final_by_step.extend([candidate_id for candidate_id in stronger_step_ids if candidate_id not in set(required_step_ids)])
        elif stronger_step_ids:
            final_by_step.extend(stronger_step_ids)
        else:
            final_by_step.extend(ordered_step_ids)
        covered_step_ids.append(step.step_id)

    outside_proof_strong_ids = [
        candidate_id
        for candidate_id in selected_order
        if candidate_id in strong_ids and candidate_id not in proof_step_ids
    ]
    if selection.proof_steps:
        final_ids = _ordered_unique([*final_by_step, *outside_proof_strong_ids])
        strategy = "proof_step_coverage"
    else:
        final_ids = _ordered_unique([*answer_ids, *verifier_ids])
        strategy = "answer_verifier_no_proof_steps"

    final_set = set(final_ids)
    answer_set = set(answer_ids)
    return ProvenanceReconciliationDecision(
        final_citation_candidate_ids=final_ids,
        dropped_citation_candidate_ids=[candidate_id for candidate_id in all_input_ids if candidate_id not in final_set],
        added_citation_candidate_ids=[candidate_id for candidate_id in final_ids if candidate_id not in answer_set],
        covered_proof_step_ids=covered_step_ids,
        uncovered_proof_step_ids=uncovered_step_ids,
        strategy=strategy,
        rationale=(
            "Reconciled proof, answerer, and verifier citations by preserving proof-step coverage "
            "through role-eligible required proof citations while dropping background/context proof-only citations."
        ),
    )


def _step_has_final_support_citation(step, final_ids: set[str], legal_ids: set[str]) -> bool:
    return any(
        citation.candidate_id in final_ids and citation.candidate_id in legal_ids
        for citation in step.citations
        if citation.required_for_final_support and citation.role in _FINAL_SUPPORT_PROOF_ROLES
    )


def _ordered_legal_unique(values: list[str], legal_ids: set[str]) -> list[str]:
    return [candidate_id for candidate_id in _ordered_unique(values) if candidate_id in legal_ids]


def finalize_answer(
    *,
    raw_answer: str,
    verification: AnswerVerificationDecision,
    selected_evidence: list[EvidenceCandidate],
    final_citation_ids: list[str],
    verified: bool,
    verification_repair_allowed: bool,
    candidate_answers_considered: list[CandidateAnswerConsidered] | None = None,
    answer_requirements: list[AnswerRequirement] | None = None,
) -> AnswerFinalizationDecision:
    cleaned_raw = _clean_answer(raw_answer)
    corrected = _clean_optional_answer(verification.corrected_answer)
    if not verified:
        guarded = _guarded_alternative_correction(
            raw_answer=cleaned_raw,
            verification=verification,
            selected_evidence=selected_evidence,
            candidate_answers_considered=candidate_answers_considered or [],
            answer_requirements=answer_requirements or [],
            verification_repair_allowed=verification_repair_allowed,
        )
        if guarded is not None:
            return guarded
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason="answer_not_verified",
            rationale="Answer was not verified, so the generated answer was preserved.",
        )
    if not verification_repair_allowed:
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason="verifier_unavailable",
            rationale="Verifier repair was unavailable or invalid, so the generated answer was preserved.",
        )
    if corrected is None:
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=None,
            reason="no_corrected_answer",
            rationale="Verifier did not propose a corrected answer.",
        )
    if _is_noanswer(corrected):
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason="corrected_answer_noanswer",
            rationale="Verifier correction was noanswer, so the generated answer was preserved.",
        )
    if _normalize_for_answer_compare(corrected) == _normalize_for_answer_compare(cleaned_raw):
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason="correction_equivalent_to_raw_answer",
            rationale="Verifier correction was equivalent to the generated answer.",
        )

    binary_gate = _binary_correction_rejection_reason(cleaned_raw, corrected)
    if binary_gate is not None:
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason=binary_gate,
            rationale="Binary answers may only be finalized to an exact yes/no value that matches the generated answer polarity.",
        )

    type_gate = _answer_type_rejection_reason(cleaned_raw, corrected)
    if type_gate is not None:
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason=type_gate,
            rationale="Verifier correction changed a specific answer type, so the generated answer was preserved.",
        )

    length_gate = _length_rejection_reason(cleaned_raw, corrected)
    if length_gate is not None:
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason=length_gate,
            rationale="Verifier correction was too expansive relative to the generated answer.",
        )

    selected_text = " ".join(candidate.text for candidate in selected_evidence)
    corrected_tokens = _meaningful_tokens(corrected)
    if corrected_tokens and not corrected_tokens.issubset(_meaningful_tokens(selected_text)):
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason="correction_not_supported_by_selected_evidence",
            rationale="Verifier correction introduced tokens that were not present in selected evidence text.",
        )

    evidence_by_id = {candidate.candidate_id: candidate for candidate in selected_evidence}
    supporting_ids = [
        candidate_id
        for candidate_id in _ordered_unique(final_citation_ids)
        if candidate_id in evidence_by_id and _candidate_text_supports_answer(evidence_by_id[candidate_id].text, corrected)
    ]
    if not supporting_ids:
        return _answer_finalization_rejected(
            raw_answer=cleaned_raw,
            corrected_answer=corrected,
            reason="correction_not_supported_by_final_citations",
            rationale="No final citation text directly supported the verifier correction.",
        )

    return AnswerFinalizationDecision(
        raw_answer=cleaned_raw,
        final_answer=corrected,
        corrected_answer=corrected,
        answer_changed=True,
        accepted=True,
        rejected_reason=None,
        supporting_candidate_ids=supporting_ids,
        strategy="verifier_corrected_answer_evidence_gated",
        rationale="Accepted verifier correction because it was verified, type-compatible, concise, and supported by final citation text.",
    )


def _guarded_alternative_correction(
    *,
    raw_answer: str,
    verification: AnswerVerificationDecision,
    selected_evidence: list[EvidenceCandidate],
    candidate_answers_considered: list[CandidateAnswerConsidered],
    answer_requirements: list[AnswerRequirement],
    verification_repair_allowed: bool,
) -> AnswerFinalizationDecision | None:
    if not verification_repair_allowed:
        return None
    better = [alternative for alternative in verification.alternative_answers if alternative.better_than_proposed_answer]
    if len(better) != 1:
        return None
    alternative = better[0]
    if alternative.missing_requirement_ids:
        return None
    requirement_ids = {requirement.requirement_id for requirement in answer_requirements}
    if requirement_ids and not requirement_ids.issubset(set(alternative.satisfied_requirement_ids)):
        return None
    evidence_by_id = {candidate.candidate_id: candidate for candidate in selected_evidence}
    if not alternative.candidate_ids or any(candidate_id not in evidence_by_id for candidate_id in alternative.candidate_ids):
        return None
    corrected = _clean_answer(verification.corrected_answer or alternative.answer)
    if not corrected or _is_noanswer(corrected):
        return None
    selected_answer = next((candidate for candidate in candidate_answers_considered if candidate.selected), None)
    selected_type = selected_answer.answer_type if selected_answer is not None else None
    alternative_candidate = _matching_candidate_answer(candidate_answers_considered, alternative.answer)
    alternative_type = alternative_candidate.answer_type if alternative_candidate is not None else None
    if selected_type and alternative_type and selected_type != alternative_type:
        return None
    if _length_rejection_reason(raw_answer, corrected) is not None and selected_type == alternative_type:
        return None
    support_text = " ".join(evidence_by_id[candidate_id].text for candidate_id in alternative.candidate_ids)
    corrected_tokens = _meaningful_tokens(corrected)
    if corrected_tokens and not corrected_tokens.issubset(_meaningful_tokens(support_text)):
        return None
    supporting_ids = [
        candidate_id
        for candidate_id in _ordered_unique(alternative.candidate_ids)
        if _candidate_text_supports_answer(evidence_by_id[candidate_id].text, corrected)
    ]
    if not supporting_ids:
        return None
    return AnswerFinalizationDecision(
        raw_answer=raw_answer,
        final_answer=corrected,
        corrected_answer=corrected,
        answer_changed=True,
        accepted=True,
        rejected_reason=None,
        supporting_candidate_ids=supporting_ids,
        strategy="guarded_better_alternative_correction",
        rationale="Accepted a single verifier-backed better alternative because it satisfied all answer requirements and was supported by selected evidence text.",
    )


def _matching_candidate_answer(
    candidate_answers_considered: list[CandidateAnswerConsidered],
    answer: str,
) -> CandidateAnswerConsidered | None:
    normalized = _normalize_for_answer_compare(answer)
    return next(
        (candidate for candidate in candidate_answers_considered if _normalize_for_answer_compare(candidate.answer) == normalized),
        None,
    )


def _answer_finalization_rejected(
    *,
    raw_answer: str,
    corrected_answer: str | None,
    reason: str,
    rationale: str,
) -> AnswerFinalizationDecision:
    return AnswerFinalizationDecision(
        raw_answer=raw_answer,
        final_answer=raw_answer,
        corrected_answer=corrected_answer,
        answer_changed=False,
        accepted=False,
        rejected_reason=reason,
        supporting_candidate_ids=[],
        strategy="keep_raw_answer",
        rationale=rationale,
    )


def _clean_answer(value: str) -> str:
    return " ".join(value.strip().split())


def _clean_optional_answer(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _clean_answer(value)
    return cleaned or None


def _is_noanswer(value: str) -> bool:
    return _normalize_for_answer_compare(value) == "noanswer"


def _normalize_for_answer_compare(value: str) -> str:
    return " ".join(_tokens(value))


def _binary_answer(value: str) -> str | None:
    normalized = _normalize_for_answer_compare(value)
    if normalized in {"yes", "no"}:
        return normalized
    parts = normalized.split()
    if parts and parts[0] in {"yes", "no"}:
        return parts[0]
    return None


def _binary_correction_rejection_reason(raw_answer: str, corrected_answer: str) -> str | None:
    raw_binary = _binary_answer(raw_answer)
    corrected_binary = _binary_answer(corrected_answer)
    if raw_binary is None and corrected_binary is None:
        return None
    if corrected_binary is None or _normalize_for_answer_compare(corrected_answer) not in {"yes", "no"}:
        return "binary_correction_not_exact"
    if raw_binary is not None and raw_binary != corrected_binary:
        return "binary_answer_polarity_changed"
    if raw_binary is None:
        return "answer_type_changed"
    return None


def _answer_type_rejection_reason(raw_answer: str, corrected_answer: str) -> str | None:
    raw_type = _specific_answer_type(raw_answer)
    corrected_type = _specific_answer_type(corrected_answer)
    if raw_type is not None and corrected_type is not None and raw_type != corrected_type:
        return "answer_type_changed"
    return None


def _specific_answer_type(value: str) -> str | None:
    normalized = _normalize_for_answer_compare(value)
    if normalized in {"yes", "no"}:
        return "binary"
    tokens = normalized.split()
    month_tokens = {
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
    }
    if any(token in month_tokens for token in tokens) or any(token.isdigit() and len(token) == 4 for token in tokens):
        return "date"
    if any(token.isdigit() for token in tokens):
        return "number"
    return None


def _length_rejection_reason(raw_answer: str, corrected_answer: str) -> str | None:
    raw_tokens = _meaningful_tokens(raw_answer)
    corrected_tokens = _meaningful_tokens(corrected_answer)
    if not corrected_tokens:
        return "corrected_answer_has_no_meaningful_tokens"
    if raw_tokens and raw_tokens.issubset(corrected_tokens):
        return None
    if len(corrected_tokens) > max(len(raw_tokens) + 3, len(raw_tokens) * 2):
        return "correction_too_expansive"
    return None


def _candidate_text_supports_answer(candidate_text: str, answer: str) -> bool:
    normalized_text = _normalize_for_answer_compare(candidate_text)
    normalized_answer = _normalize_for_answer_compare(answer)
    if normalized_answer and normalized_answer in normalized_text:
        return True
    answer_tokens = _meaningful_tokens(answer)
    return bool(answer_tokens) and answer_tokens.issubset(_meaningful_tokens(candidate_text))


def _meaningful_tokens(text: str) -> set[str]:
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "both", "by", "for", "from", "in", "is", "it",
        "of", "on", "or", "the", "to", "was", "were", "who", "whom", "whose", "with",
    }
    return {token for token in _tokens(text) if token not in stopwords}


def _step_metadata(
    metadata: dict[str, object] | None,
    decision_point: LLMDecisionPoint,
    aliases: _CandidateIdAliases | None = None,
) -> dict[str, object]:
    merged = dict(metadata or {})
    merged["transition_type"] = decision_point.value
    if aliases is not None:
        merged["candidate_id_aliases"] = aliases.trace_metadata()
    return merged


def _tokens(text: str) -> set[str]:
    return {token for token in "".join(char.lower() if char.isalnum() else " " for char in text).split() if token}


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return float(len(left_tokens & right_tokens)) / float(len(left_tokens | right_tokens))


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
