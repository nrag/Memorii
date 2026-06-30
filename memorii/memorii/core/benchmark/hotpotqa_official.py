"""Official-compatible HotpotQA prediction and metric helpers."""

from __future__ import annotations

import json
import re
import string
from collections import Counter
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from memorii.core.benchmark.hotpotqa import HotpotQAExample
from memorii.core.grounding.models import (
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
from memorii.core.llm_decision.models import (
    LLMDecisionMode,
    LLMDecisionPoint,
    LLMDecisionStatus,
    LLMDecisionTrace,
)
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


class HotpotQASentenceCandidate(BaseModel):
    title: str
    sentence_index: int
    text: str

    model_config = ConfigDict(extra="forbid")


class HotpotQAAnswerContext(BaseModel):
    example_id: str
    question: str
    question_type: str | None = None
    candidates: list[HotpotQASentenceCandidate] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class HotpotQASupportingFact(BaseModel):
    title: str
    sentence_index: int

    model_config = ConfigDict(extra="forbid")


class HotpotQAAnswerDecision(BaseModel):
    answer: str
    supporting_facts: list[HotpotQASupportingFact] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str

    model_config = ConfigDict(extra="forbid")


class HotpotQAPrediction(BaseModel):
    answer: dict[str, str] = Field(default_factory=dict)
    sp: dict[str, list[tuple[str, int]]] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class HotpotQAExampleScore(BaseModel):
    answer_em: float
    answer_f1: float
    answer_precision: float
    answer_recall: float
    support_em: float
    support_f1: float
    support_precision: float
    support_recall: float
    joint_em: float
    joint_f1: float
    joint_precision: float
    joint_recall: float

    model_config = ConfigDict(extra="forbid")


def hotpotqa_answer_context_for_example(example: HotpotQAExample) -> HotpotQAAnswerContext:
    candidates: list[HotpotQASentenceCandidate] = []
    for paragraph in example.context:
        for index, sentence in enumerate(paragraph.sentences):
            candidates.append(
                HotpotQASentenceCandidate(
                    title=paragraph.title,
                    sentence_index=index,
                    text=sentence,
                )
            )
    return HotpotQAAnswerContext(
        example_id=example.example_id,
        question=example.question,
        question_type=example.question_type,
        candidates=candidates,
    )


def expected_hotpotqa_answer_decision(example: HotpotQAExample) -> HotpotQAAnswerDecision:
    return HotpotQAAnswerDecision(
        answer=example.answer,
        supporting_facts=[
            HotpotQASupportingFact(title=title, sentence_index=sentence_index)
            for title, sentence_index in example.supporting_facts
        ],
        confidence=1.0,
        rationale="expected HotpotQA gold answer and supporting facts",
    )


def rule_hotpotqa_answer_decision(example: HotpotQAExample) -> HotpotQAAnswerDecision:
    context = hotpotqa_answer_context_for_example(example)
    ranked = sorted(
        context.candidates,
        key=lambda item: (_lexical_overlap(example.question, f"{item.title} {item.text}"), item.title, item.sentence_index),
        reverse=True,
    )
    supporting_facts = [
        HotpotQASupportingFact(title=item.title, sentence_index=item.sentence_index)
        for item in ranked[:2]
    ]
    answer = _extract_rule_answer(example=example, ranked=ranked)
    return HotpotQAAnswerDecision(
        answer=answer,
        supporting_facts=supporting_facts,
        confidence=0.35,
        rationale="rule baseline uses shallow lexical sentence overlap and extractive answer fallback",
    )


def validate_hotpotqa_answer_decision(
    *,
    context: HotpotQAAnswerContext,
    decision: HotpotQAAnswerDecision,
) -> tuple[bool, list[str]]:
    legal = {(candidate.title, candidate.sentence_index) for candidate in context.candidates}
    errors: list[str] = []
    if not decision.answer.strip():
        errors.append("answer_empty")
    for fact in decision.supporting_facts:
        if (fact.title, fact.sentence_index) not in legal:
            errors.append(f"invalid_supporting_fact:{fact.title}:{fact.sentence_index}")
    return not errors, errors


def supporting_fact_pairs(decision: HotpotQAAnswerDecision) -> list[tuple[str, int]]:
    return [(fact.title, fact.sentence_index) for fact in decision.supporting_facts]


def hotpotqa_evidence_context_for_example(example: HotpotQAExample) -> EvidenceSelectionContext:
    candidates: list[EvidenceCandidate] = []
    for paragraph_index, paragraph in enumerate(example.context):
        for sentence_index, sentence in enumerate(paragraph.sentences):
            candidates.append(
                EvidenceCandidate(
                    candidate_id=hotpotqa_candidate_id(
                        example_id=example.example_id,
                        paragraph_index=paragraph_index,
                        sentence_index=sentence_index,
                    ),
                    source_id=paragraph.title,
                    title=paragraph.title,
                    position=sentence_index,
                    text=sentence,
                    metadata={
                        "example_id": example.example_id,
                        "question_type": example.question_type,
                        "paragraph_index": paragraph_index,
                        "sentence_index": sentence_index,
                    },
                )
            )
    return EvidenceSelectionContext(
        query=example.question,
        candidates=candidates,
        answer_format="short_answer",
        metadata={
            "example_id": example.example_id,
            "question_type": example.question_type,
            "task": "grounded_question_answering",
        },
    )


def hotpotqa_candidate_id(*, example_id: str, paragraph_index: int, sentence_index: int) -> str:
    return f"hotpotqa:{example_id}:{paragraph_index}:{sentence_index}"


def hotpotqa_supporting_fact_candidate_ids(example: HotpotQAExample) -> list[str]:
    ids: list[str] = []
    for title, sentence_index in example.supporting_facts:
        for paragraph_index, paragraph in enumerate(example.context):
            if paragraph.title == title and 0 <= sentence_index < len(paragraph.sentences):
                ids.append(
                    hotpotqa_candidate_id(
                        example_id=example.example_id,
                        paragraph_index=paragraph_index,
                        sentence_index=sentence_index,
                    )
                )
                break
    return ids


def hotpotqa_supporting_fact_pairs_from_candidate_ids(
    *,
    example: HotpotQAExample,
    candidate_ids: list[str],
) -> list[tuple[str, int]]:
    candidate_by_id = {
        candidate.candidate_id: candidate
        for candidate in hotpotqa_evidence_context_for_example(example).candidates
    }
    pairs: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for candidate_id in candidate_ids:
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            continue
        sentence_index = candidate.metadata.get("sentence_index")
        if not isinstance(candidate.title, str) or not isinstance(sentence_index, int):
            continue
        pair = (candidate.title, sentence_index)
        if pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def expected_hotpotqa_grounding_decisions(
    example: HotpotQAExample,
) -> tuple[EvidenceSelectionDecision, GroundedAnswerDecision, AnswerVerificationDecision]:
    selected = hotpotqa_supporting_fact_candidate_ids(example)
    context = hotpotqa_evidence_context_for_example(example)
    all_ids = [candidate.candidate_id for candidate in context.candidates]
    excluded = [candidate_id for candidate_id in all_ids if candidate_id not in set(selected)]
    answer_requirements = [
        AnswerRequirement(
            requirement_id=f"requirement:{index + 1}",
            description="Expected evidence satisfies a required answer constraint.",
            requirement_type="direct_answer" if index == len(selected) - 1 else "bridge_entity",
            candidate_ids=[candidate_id],
            rationale="Deterministic dry-run requirement for expected supporting evidence.",
        )
        for index, candidate_id in enumerate(selected)
    ]
    return (
        EvidenceSelectionDecision(
            selected_candidate_ids=selected,
            excluded_candidate_ids=excluded,
            ranking=[*selected, *excluded],
            proof_steps=[
                ProofStep(
                    step_id=f"step:{index + 1}",
                    description="Evidence needed to support the grounded answer.",
                    candidate_ids=[candidate_id],
                    required_candidate_ids=[candidate_id],
                    citations=[
                        ProofStepCitation(
                            candidate_id=candidate_id,
                            role="direct_answer" if index == len(selected) - 1 else "bridge",
                            required_for_final_support=True,
                            claim_supported="This evidence is part of the expected grounded proof.",
                            rationale="Expected supporting evidence for deterministic dry-run.",
                        )
                    ],
                    rationale="Expected supporting evidence for deterministic dry-run.",
                )
                for index, candidate_id in enumerate(selected)
            ],
            confidence=1.0,
            rationale="expected evidence selection for deterministic dry-run",
            failure_mode=None,
            requires_judge_review=False,
        ),
        GroundedAnswerDecision(
            answer=example.answer,
            citation_candidate_ids=selected,
            answer_requirements=answer_requirements,
            candidate_answers_considered=[
                CandidateAnswerConsidered(
                    answer=example.answer,
                    candidate_ids=selected,
                    selected=True,
                    answer_type=_expected_grounded_answer_type(example.answer),
                    requirement_coverage=[
                        CandidateRequirementCoverage(
                            requirement_id=requirement.requirement_id,
                            satisfied=True,
                            candidate_ids=requirement.candidate_ids,
                            rationale="Expected answer satisfies this deterministic dry-run requirement.",
                        )
                        for requirement in answer_requirements
                    ],
                    satisfied_requirement_ids=[requirement.requirement_id for requirement in answer_requirements],
                    missing_requirement_ids=[],
                    rationale="Expected answer for deterministic dry-run.",
                )
            ],
            answer_type=_expected_grounded_answer_type(example.answer),
            answer_span_candidate_id=selected[-1] if selected else None,
            answer_span_text=example.answer if selected else None,
            confidence=1.0,
            rationale="expected grounded answer for deterministic dry-run",
            failure_mode=None,
            requires_judge_review=False,
        ),
        AnswerVerificationDecision(
            entailed=True,
            corrected_answer=None,
            required_candidate_ids=selected,
            missing_candidate_ids=[],
            question_constraints=[
                QuestionConstraintCoverage(
                    constraint_id=f"constraint:{index + 1}",
                    description="Expected evidence satisfies a required question constraint.",
                    satisfied=True,
                    candidate_ids=[candidate_id],
                    rationale="Deterministic dry-run uses gold supporting evidence as satisfied constraints.",
                )
                for index, candidate_id in enumerate(selected)
            ],
            alternative_answers=[],
            confidence=1.0,
            rationale="expected answer verification for deterministic dry-run",
            failure_mode=None,
            requires_judge_review=False,
        ),
    )


def _expected_grounded_answer_type(answer: str) -> str:
    normalized = _normalize_answer(answer)
    if normalized in {"yes", "no"}:
        return "yes_no"
    if normalized == "noanswer":
        return "noanswer"
    if any(token.isdigit() for token in normalized.split()):
        return "number"
    return "short_span"


def hotpotqa_answer_format_diagnostic(*, raw_answer: str, gold_answer: str) -> dict[str, object]:
    normalized_gold = _normalize_answer(gold_answer)
    normalized_raw = _normalize_answer(raw_answer)
    gold_is_binary = normalized_gold in {"yes", "no", "noanswer"}
    match = re.match(r"^(yes|no)\b", raw_answer.strip().lower())
    raw_binary_prefix = match.group(1) if match else None
    return {
        "normalized_raw_answer": normalized_raw,
        "normalized_gold_answer": normalized_gold,
        "gold_is_binary": gold_is_binary,
        "raw_binary_prefix": raw_binary_prefix,
        "binary_prefix_matches_gold": gold_is_binary and raw_binary_prefix == normalized_gold,
        "verbose_binary_answer": bool(
            gold_is_binary
            and raw_binary_prefix == normalized_gold
            and normalized_raw != normalized_gold
        ),
    }


def hotpotqa_answer_trace_for_rule(
    *,
    context: HotpotQAAnswerContext,
    decision: HotpotQAAnswerDecision,
    mode: str,
) -> LLMDecisionTrace:
    return LLMDecisionTrace(
        trace_id=f"trace:{uuid4().hex}",
        decision_point=LLMDecisionPoint.HOTPOTQA_ANSWER,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )


def hotpotqa_answer_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    rule_output: dict[str, object],
    context: HotpotQAAnswerContext,
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.HOTPOTQA_ANSWER,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, "llm_decision_failed"
    try:
        decision = HotpotQAAnswerDecision.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.HOTPOTQA_ANSWER,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    is_valid, validation_errors = validate_hotpotqa_answer_decision(context=context, decision=decision)
    if not is_valid:
        failed_result = result.model_copy(update={"failure_mode": ",".join(validation_errors)})
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.HOTPOTQA_ANSWER,
            mode=mode,
            result=failed_result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.HOTPOTQA_ANSWER,
        mode=mode,
        result=result.model_copy(update={"output": output}),
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None


def fake_llm_result_for_hotpotqa_answer(
    *,
    request: LLMStructuredRequest,
    decision: HotpotQAAnswerDecision,
    provider_name: str = "fake",
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


def evaluate_hotpotqa_predictions(
    *,
    prediction: HotpotQAPrediction,
    gold_examples: list[HotpotQAExample],
) -> dict[str, float]:
    """Evaluate HotpotQA predictions using the official v1 metric logic.

    The metric formulas are ported from the official HotpotQA evaluator:
    https://github.com/hotpotqa/hotpot/blob/master/hotpot_evaluate_v1.py
    """
    metrics = {
        "em": 0.0,
        "f1": 0.0,
        "prec": 0.0,
        "recall": 0.0,
        "sp_em": 0.0,
        "sp_f1": 0.0,
        "sp_prec": 0.0,
        "sp_recall": 0.0,
        "joint_em": 0.0,
        "joint_f1": 0.0,
        "joint_prec": 0.0,
        "joint_recall": 0.0,
    }
    if not gold_examples:
        return metrics

    for example in gold_examples:
        score = score_hotpotqa_example(
            prediction_answer=prediction.answer.get(example.example_id, ""),
            prediction_supporting_facts=prediction.sp.get(example.example_id, []),
            example=example,
        )
        metrics["em"] += score.answer_em
        metrics["f1"] += score.answer_f1
        metrics["prec"] += score.answer_precision
        metrics["recall"] += score.answer_recall
        metrics["sp_em"] += score.support_em
        metrics["sp_f1"] += score.support_f1
        metrics["sp_prec"] += score.support_precision
        metrics["sp_recall"] += score.support_recall
        metrics["joint_em"] += score.joint_em
        metrics["joint_f1"] += score.joint_f1
        metrics["joint_prec"] += score.joint_precision
        metrics["joint_recall"] += score.joint_recall

    count = float(len(gold_examples))
    return {key: value / count for key, value in metrics.items()}


def score_hotpotqa_example(
    *,
    prediction_answer: str,
    prediction_supporting_facts: list[tuple[str, int]],
    example: HotpotQAExample,
) -> HotpotQAExampleScore:
    answer_em = float(_exact_match_score(prediction_answer, example.answer))
    answer_f1, answer_precision, answer_recall = _f1_score(prediction_answer, example.answer)
    support_em, support_f1, support_precision, support_recall = _sp_scores(
        prediction_supporting_facts,
        example.supporting_facts,
    )
    joint_precision = answer_precision * support_precision
    joint_recall = answer_recall * support_recall
    return HotpotQAExampleScore(
        answer_em=answer_em,
        answer_f1=answer_f1,
        answer_precision=answer_precision,
        answer_recall=answer_recall,
        support_em=support_em,
        support_f1=support_f1,
        support_precision=support_precision,
        support_recall=support_recall,
        joint_em=answer_em * support_em,
        joint_f1=_f1_from_precision_recall(joint_precision, joint_recall),
        joint_precision=joint_precision,
        joint_recall=joint_recall,
    )


def build_hotpotqa_error_analysis(
    *,
    examples: list[HotpotQAExample],
    answer_rows: list[dict[str, object]],
) -> dict[str, object]:
    row_by_id = {str(row["example_id"]): row for row in answer_rows}
    by_question_type: dict[str, dict[str, int]] = {}
    representative_failures: list[dict[str, object]] = []
    summary = {
        "examples": len(examples),
        "answer_f1_failures": 0,
        "support_f1_failures": 0,
        "joint_f1_failures": 0,
        "binary_answer_format_maybe_cost_f1": 0,
        "support_extra_fact_examples": 0,
        "support_missing_fact_examples": 0,
        "answer_correct_support_wrong": 0,
        "answer_wrong_support_correct": 0,
        "both_wrong": 0,
    }

    for example in examples:
        row = row_by_id.get(example.example_id, {})
        scores = row.get("scores")
        if not isinstance(scores, dict):
            predicted_support = _pairs_from_value(row.get("predicted_supporting_facts", []))
            scores = score_hotpotqa_example(
                prediction_answer=str(row.get("exported_answer", "")),
                prediction_supporting_facts=predicted_support,
                example=example,
            ).model_dump(mode="json")
        else:
            predicted_support = _pairs_from_value(row.get("predicted_supporting_facts", []))

        gold_support = set(map(tuple, example.supporting_facts))
        predicted_support_set = set(predicted_support)
        extra_support = sorted(predicted_support_set - gold_support)
        missing_support = sorted(gold_support - predicted_support_set)
        question_type = example.question_type or "unknown"
        bucket = by_question_type.setdefault(
            question_type,
            {
                "examples": 0,
                "answer_f1_failures": 0,
                "support_f1_failures": 0,
                "joint_f1_failures": 0,
            },
        )
        bucket["examples"] += 1

        answer_failed = float(scores.get("answer_f1", 0.0)) < 1.0
        support_failed = float(scores.get("support_f1", 0.0)) < 1.0
        joint_failed = float(scores.get("joint_f1", 0.0)) < 1.0
        if answer_failed:
            summary["answer_f1_failures"] += 1
            bucket["answer_f1_failures"] += 1
        if support_failed:
            summary["support_f1_failures"] += 1
            bucket["support_f1_failures"] += 1
        if joint_failed:
            summary["joint_f1_failures"] += 1
            bucket["joint_f1_failures"] += 1
        format_diagnostic = row.get("answer_format_diagnostic")
        if not isinstance(format_diagnostic, dict):
            format_diagnostic = hotpotqa_answer_format_diagnostic(
                raw_answer=str(row.get("raw_answer", row.get("exported_answer", ""))),
                gold_answer=example.answer,
            )
        if bool(format_diagnostic.get("verbose_binary_answer")) and answer_failed:
            summary["binary_answer_format_maybe_cost_f1"] += 1
        if extra_support:
            summary["support_extra_fact_examples"] += 1
        if missing_support:
            summary["support_missing_fact_examples"] += 1
        if not answer_failed and support_failed:
            summary["answer_correct_support_wrong"] += 1
        elif answer_failed and not support_failed:
            summary["answer_wrong_support_correct"] += 1
        elif answer_failed and support_failed:
            summary["both_wrong"] += 1

        if joint_failed and len(representative_failures) < 20:
            representative_failures.append(
                {
                    "example_id": example.example_id,
                    "question_type": question_type,
                    "question": example.question,
                    "expected_answer": example.answer,
                    "raw_answer": row.get("raw_answer", row.get("exported_answer", "")),
                    "exported_answer": row.get("exported_answer", ""),
                    "answer_format_diagnostic": format_diagnostic,
                    "expected_supporting_facts": list(example.supporting_facts),
                    "predicted_supporting_facts": list(predicted_support),
                    "extra_supporting_facts": extra_support,
                    "missing_supporting_facts": missing_support,
                    "scores": scores,
                }
            )

    return {
        "summary": summary,
        "by_question_type": by_question_type,
        "representative_failures": representative_failures,
    }


def build_hotpotqa_stage_diagnostics(
    *,
    examples: list[HotpotQAExample],
    answer_rows: list[dict[str, object]],
) -> dict[str, object]:
    row_by_id = {str(row["example_id"]): row for row in answer_rows}
    rows: list[dict[str, object]] = []
    summary = {
        "examples": len(examples),
        "proof_full_support_count": 0,
        "answer_citation_full_support_count": 0,
        "verifier_citation_full_support_count": 0,
        "final_citation_full_support_count": 0,
        "wrong_answer_verified_count": 0,
        "proof_had_support_final_lost_support_count": 0,
        "answer_correct_support_bad_count": 0,
        "support_correct_answer_bad_count": 0,
        "both_bad_count": 0,
        "perfect_count": 0,
        "no_alternative_challenge_count": 0,
        "candidate_answer_count_distribution": {},
        "selected_candidate_missing_requirement_count": 0,
        "better_candidate_available_count": 0,
        "no_candidate_competition_count": 0,
        "answer_correct_but_verifier_rejected_count": 0,
        "guarded_correction_attempted_count": 0,
        "guarded_correction_accepted_count": 0,
        "guarded_correction_rejected_count": 0,
    }
    candidate_answer_count_distribution: Counter[int] = Counter()
    citation_views: dict[str, list[list[tuple[str, int]]]] = {
        "proof": [],
        "required_proof": [],
        "role_eligible_proof": [],
        "answerer": [],
        "verifier": [],
        "answerer_verifier": [],
        "final": [],
    }
    gold_views: list[list[tuple[str, int]]] = []

    for example in examples:
        row = row_by_id.get(example.example_id, {})
        scores = row.get("scores") if isinstance(row.get("scores"), dict) else {}
        answer_f1 = float(scores.get("answer_f1", 0.0))
        support_f1 = float(scores.get("support_f1", 0.0))
        answer_correct = answer_f1 == 1.0
        support_correct = support_f1 == 1.0
        if answer_correct and support_correct:
            answer_bucket = "perfect"
            summary["perfect_count"] += 1
        elif answer_correct:
            answer_bucket = "answer_ok_support_bad"
            summary["answer_correct_support_bad_count"] += 1
        elif support_correct:
            answer_bucket = "support_ok_answer_bad"
            summary["support_correct_answer_bad_count"] += 1
        else:
            answer_bucket = "both_bad"
            summary["both_bad_count"] += 1

        gold_support = set(map(tuple, example.supporting_facts))
        proof_support = set(_pairs_from_value(row.get("proof_supporting_facts", [])))
        answer_support = set(_pairs_from_value(row.get("answer_supporting_facts", [])))
        verifier_support = set(_pairs_from_value(row.get("verified_supporting_facts", [])))
        final_support = set(_pairs_from_value(row.get("predicted_supporting_facts", [])))
        required_proof_support = set(_pairs_from_value(row.get("required_proof_supporting_facts", [])))
        role_eligible_proof_support = set(_pairs_from_value(row.get("role_eligible_proof_supporting_facts", [])))
        citation_views["proof"].append(sorted(proof_support))
        citation_views["required_proof"].append(sorted(required_proof_support))
        citation_views["role_eligible_proof"].append(sorted(role_eligible_proof_support))
        citation_views["answerer"].append(sorted(answer_support))
        citation_views["verifier"].append(sorted(verifier_support))
        citation_views["answerer_verifier"].append(sorted(answer_support | verifier_support))
        citation_views["final"].append(sorted(final_support))
        gold_views.append(list(example.supporting_facts))
        proof_has_full = bool(gold_support) and gold_support <= proof_support
        answer_has_full = bool(gold_support) and gold_support <= answer_support
        verifier_has_full = bool(gold_support) and gold_support <= verifier_support
        final_has_full = bool(gold_support) and gold_support <= final_support
        summary["proof_full_support_count"] += int(proof_has_full)
        summary["answer_citation_full_support_count"] += int(answer_has_full)
        summary["verifier_citation_full_support_count"] += int(verifier_has_full)
        summary["final_citation_full_support_count"] += int(final_has_full)
        proof_to_final_loss = proof_has_full and not final_has_full
        summary["proof_had_support_final_lost_support_count"] += int(proof_to_final_loss)

        answer_verification = row.get("answer_verification") if isinstance(row.get("answer_verification"), dict) else {}
        constraints = answer_verification.get("question_constraints") if isinstance(answer_verification, dict) else []
        if not isinstance(constraints, list):
            constraints = []
        alternative_answers = answer_verification.get("alternative_answers") if isinstance(answer_verification, dict) else []
        if not isinstance(alternative_answers, list):
            alternative_answers = []
        grounded_answer = row.get("grounded_answer") if isinstance(row.get("grounded_answer"), dict) else {}
        candidate_answers = grounded_answer.get("candidate_answers_considered") if isinstance(grounded_answer, dict) else []
        if not isinstance(candidate_answers, list):
            candidate_answers = []
        candidate_answer_count_distribution[len(candidate_answers)] += 1
        selected_candidates = [candidate for candidate in candidate_answers if isinstance(candidate, dict) and candidate.get("selected")]
        selected_missing_requirement_ids = [
            item
            for candidate in selected_candidates
            for item in candidate.get("missing_requirement_ids", [])
            if isinstance(item, str)
        ]
        better_candidate_available = any(
            isinstance(alternative, dict) and bool(alternative.get("better_than_proposed_answer"))
            for alternative in alternative_answers
        )
        no_candidate_competition = len(candidate_answers) <= 1
        finalization = row.get("answer_finalization") if isinstance(row.get("answer_finalization"), dict) else {}
        finalization_strategy = str(finalization.get("strategy") or "")
        guarded_attempted = better_candidate_available
        guarded_accepted = finalization_strategy == "guarded_better_alternative_correction"
        guarded_rejected = guarded_attempted and not guarded_accepted
        summary["selected_candidate_missing_requirement_count"] += int(bool(selected_missing_requirement_ids))
        summary["better_candidate_available_count"] += int(better_candidate_available)
        summary["no_candidate_competition_count"] += int(no_candidate_competition)
        summary["answer_correct_but_verifier_rejected_count"] += int(answer_correct and not bool(row.get("verified")))
        summary["guarded_correction_attempted_count"] += int(guarded_attempted)
        summary["guarded_correction_accepted_count"] += int(guarded_accepted)
        summary["guarded_correction_rejected_count"] += int(guarded_rejected)
        uncovered_constraints = [
            constraint for constraint in constraints
            if isinstance(constraint, dict) and not bool(constraint.get("satisfied"))
        ]
        constraints_without_evidence = [
            constraint for constraint in constraints
            if isinstance(constraint, dict) and bool(constraint.get("satisfied")) and not constraint.get("candidate_ids")
        ]
        no_alternative_challenge = len(alternative_answers) == 0
        summary["no_alternative_challenge_count"] += int(no_alternative_challenge)

        verified = bool(row.get("verified"))
        wrong_answer_but_verified = verified and not answer_correct
        verified_false_answer_correct = not verified and answer_correct
        summary["wrong_answer_verified_count"] += int(wrong_answer_but_verified)

        missing_support = sorted(gold_support - final_support)
        extra_support = sorted(final_support - gold_support)
        near_title_distractor_count = sum(
            1
            for missing in missing_support
            if any(extra[1] == missing[1] and extra[0] != missing[0] for extra in extra_support)
        )
        rows.append(
            {
                "example_id": example.example_id,
                "question": example.question,
                "question_type": example.question_type or "unknown",
                "answer_bucket": answer_bucket,
                "answer_f1": answer_f1,
                "support_f1": support_f1,
                "proof_has_full_gold_support": proof_has_full,
                "answer_citations_have_full_gold_support": answer_has_full,
                "verifier_citations_have_full_gold_support": verifier_has_full,
                "final_citations_have_full_gold_support": final_has_full,
                "proof_to_final_citation_loss": proof_to_final_loss,
                "wrong_answer_but_verified": wrong_answer_but_verified,
                "verified_false_while_answer_correct": verified_false_answer_correct,
                "constraint_count": len(constraints),
                "uncovered_constraint_count": len(uncovered_constraints),
                "constraints_without_evidence_count": len(constraints_without_evidence),
                "no_alternative_challenge": no_alternative_challenge,
                "answer_finalization_reason": finalization.get("rejected_reason") or "accepted",
                "candidate_answer_count": len(candidate_answers),
                "selected_candidate_missing_requirement_ids": selected_missing_requirement_ids,
                "better_candidate_available": better_candidate_available,
                "no_candidate_competition": no_candidate_competition,
                "guarded_correction_attempted": guarded_attempted,
                "guarded_correction_accepted": guarded_accepted,
                "guarded_correction_rejected": guarded_rejected,
                "support_missing_count": len(missing_support),
                "support_extra_count": len(extra_support),
                "near_title_distractor_count": near_title_distractor_count,
                "missing_supporting_facts": missing_support,
                "extra_supporting_facts": extra_support,
            }
        )

    summary["candidate_answer_count_distribution"] = {
        str(key): value for key, value in sorted(candidate_answer_count_distribution.items())
    }
    summary["citation_view_metrics"] = _citation_view_metrics(citation_views=citation_views, gold_views=gold_views)
    return {"summary": summary, "rows": rows}


def _citation_view_metrics(
    *,
    citation_views: dict[str, list[list[tuple[str, int]]]],
    gold_views: list[list[tuple[str, int]]],
) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    count = len(gold_views)
    for view_name, predictions in citation_views.items():
        totals = {
            "support_em": 0.0,
            "support_f1": 0.0,
            "support_precision": 0.0,
            "support_recall": 0.0,
            "full_gold_support_count": 0,
            "extra_support_examples": 0,
            "missing_support_examples": 0,
            "average_citation_count": 0.0,
        }
        for prediction, gold in zip(predictions, gold_views, strict=False):
            support_em, support_f1, support_precision, support_recall = _sp_scores(prediction, gold)
            prediction_set = set(map(tuple, prediction))
            gold_set = set(map(tuple, gold))
            totals["support_em"] += support_em
            totals["support_f1"] += support_f1
            totals["support_precision"] += support_precision
            totals["support_recall"] += support_recall
            totals["full_gold_support_count"] += int(bool(gold_set) and gold_set <= prediction_set)
            totals["extra_support_examples"] += int(bool(prediction_set - gold_set))
            totals["missing_support_examples"] += int(bool(gold_set - prediction_set))
            totals["average_citation_count"] += len(prediction_set)
        if count:
            for key in ["support_em", "support_f1", "support_precision", "support_recall", "average_citation_count"]:
                totals[key] = float(totals[key]) / float(count)
        metrics[view_name] = totals
    return metrics


def _normalize_answer(value: str) -> str:
    def remove_articles(text: str) -> str:
        return re.sub(r"\b(a|an|the)\b", " ", text)

    def white_space_fix(text: str) -> str:
        return " ".join(text.split())

    def remove_punc(text: str) -> str:
        exclude = set(string.punctuation)
        return "".join(char for char in text if char not in exclude)

    return white_space_fix(remove_articles(remove_punc(value.lower())))


def _f1_score(prediction: str, ground_truth: str) -> tuple[float, float, float]:
    normalized_prediction = _normalize_answer(prediction)
    normalized_ground_truth = _normalize_answer(ground_truth)
    zero_metric = (0.0, 0.0, 0.0)
    if normalized_prediction in {"yes", "no", "noanswer"} and normalized_prediction != normalized_ground_truth:
        return zero_metric
    if normalized_ground_truth in {"yes", "no", "noanswer"} and normalized_prediction != normalized_ground_truth:
        return zero_metric
    prediction_tokens = normalized_prediction.split()
    ground_truth_tokens = normalized_ground_truth.split()
    common = Counter(prediction_tokens) & Counter(ground_truth_tokens)
    num_same = sum(common.values())
    if num_same == 0:
        return zero_metric
    precision = float(num_same) / float(len(prediction_tokens))
    recall = float(num_same) / float(len(ground_truth_tokens))
    f1 = (2 * precision * recall) / (precision + recall)
    return f1, precision, recall


def _exact_match_score(prediction: str, ground_truth: str) -> bool:
    return _normalize_answer(prediction) == _normalize_answer(ground_truth)


def _update_answer(metrics: dict[str, float], prediction: str, gold: str) -> tuple[float, float, float]:
    em = float(_exact_match_score(prediction, gold))
    f1, precision, recall = _f1_score(prediction, gold)
    metrics["em"] += em
    metrics["f1"] += f1
    metrics["prec"] += precision
    metrics["recall"] += recall
    return em, precision, recall


def _update_sp(
    metrics: dict[str, float],
    prediction: list[tuple[str, int]],
    gold: list[tuple[str, int]],
) -> tuple[float, float, float]:
    em, f1, precision, recall = _sp_scores(prediction, gold)
    metrics["sp_em"] += em
    metrics["sp_f1"] += f1
    metrics["sp_prec"] += precision
    metrics["sp_recall"] += recall
    return em, precision, recall


def _sp_scores(
    prediction: list[tuple[str, int]],
    gold: list[tuple[str, int]],
) -> tuple[float, float, float, float]:
    cur_sp_pred = set(map(tuple, prediction))
    gold_sp_pred = set(map(tuple, gold))
    true_positive = len(cur_sp_pred & gold_sp_pred)
    false_positive = len(cur_sp_pred - gold_sp_pred)
    false_negative = len(gold_sp_pred - cur_sp_pred)
    precision = float(true_positive) / float(true_positive + false_positive) if true_positive + false_positive > 0 else 0.0
    recall = float(true_positive) / float(true_positive + false_negative) if true_positive + false_negative > 0 else 0.0
    f1 = _f1_from_precision_recall(precision, recall)
    em = 1.0 if false_positive + false_negative == 0 else 0.0
    return em, f1, precision, recall


def _f1_from_precision_recall(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0


def _pairs_from_value(value: object) -> list[tuple[str, int]]:
    if not isinstance(value, list):
        return []
    pairs: list[tuple[str, int]] = []
    for item in value:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            continue
        title, sentence_index = item
        if isinstance(title, str) and isinstance(sentence_index, int):
            pairs.append((title, sentence_index))
    return pairs


def _tokens(text: str) -> set[str]:
    return {token for token in "".join(char.lower() if char.isalnum() else " " for char in text).split() if token}


def _lexical_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return float(len(left_tokens & right_tokens)) / float(len(left_tokens | right_tokens))


def _extract_rule_answer(*, example: HotpotQAExample, ranked: list[HotpotQASentenceCandidate]) -> str:
    if example.question.lower().startswith("which "):
        question_tokens = _tokens(example.question)
        for candidate in ranked:
            title_tokens = _tokens(candidate.title)
            if title_tokens and not title_tokens.issubset(question_tokens):
                return candidate.title
    if ranked:
        words = ranked[0].text.replace(".", "").split()
        return " ".join(words[: min(5, len(words))]) or ranked[0].title
    return "noanswer"
