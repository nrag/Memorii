"""Deterministic comparators for offline LLM decision evals."""

from __future__ import annotations

from dataclasses import dataclass

from memorii.core.belief.models import BeliefUpdateContext, BeliefUpdateDecision
from memorii.core.promotion.models import PromotionDecision


@dataclass(frozen=True)
class ComparatorResult:
    passed: bool
    score: float
    errors: list[str]
    requires_judge_review: bool = False


_SUPPORTED_PROMOTION_FIELDS = {
    "promote",
    "target_plane",
    "min_confidence",
    "max_confidence",
    "rationale_contains",
    "requires_judge_review",
}
_SUPPORTED_BELIEF_FIELDS = {
    "min_belief",
    "max_belief",
    "direction",
    "min_confidence",
    "rationale_contains",
    "requires_judge_review",
}


def compare_promotion(
    *,
    actual: PromotionDecision,
    expected_output: dict[str, object] | None,
) -> ComparatorResult:
    if expected_output is None:
        return ComparatorResult(passed=True, score=1.0, errors=[], requires_judge_review=True)

    checks = 0
    passed_checks = 0
    errors: list[str] = []
    requires_judge_review = bool(expected_output.get("requires_judge_review") is True)

    unknown_keys = sorted(set(expected_output) - _SUPPORTED_PROMOTION_FIELDS)
    if unknown_keys:
        requires_judge_review = True
        errors.append(f"unsupported_expected_fields:{','.join(unknown_keys)}")

    if "promote" in expected_output:
        checks += 1
        if actual.promote == bool(expected_output["promote"]):
            passed_checks += 1
        else:
            errors.append("promote_mismatch")

    if "target_plane" in expected_output:
        checks += 1
        if actual.target_plane == expected_output["target_plane"]:
            passed_checks += 1
        else:
            errors.append("target_plane_mismatch")

    if "min_confidence" in expected_output:
        checks += 1
        if actual.confidence >= float(expected_output["min_confidence"]):
            passed_checks += 1
        else:
            errors.append("confidence_below_min")

    if "max_confidence" in expected_output:
        checks += 1
        if actual.confidence <= float(expected_output["max_confidence"]):
            passed_checks += 1
        else:
            errors.append("confidence_above_max")

    if "rationale_contains" in expected_output:
        checks += 1
        expected_text = str(expected_output["rationale_contains"]).lower()
        actual_text = actual.rationale.lower()
        if expected_text in actual_text:
            passed_checks += 1
        else:
            errors.append("rationale_missing_substring")

    if checks == 0:
        requires_judge_review = True
        score = 1.0
    else:
        score = passed_checks / checks

    return ComparatorResult(
        passed=passed_checks == checks,
        score=score,
        errors=errors,
        requires_judge_review=requires_judge_review,
    )


def compare_belief_update(
    *,
    context: BeliefUpdateContext,
    actual: BeliefUpdateDecision,
    expected_output: dict[str, object] | None,
) -> ComparatorResult:
    if expected_output is None:
        return ComparatorResult(passed=True, score=1.0, errors=[], requires_judge_review=True)

    checks = 0
    passed_checks = 0
    errors: list[str] = []
    requires_judge_review = bool(expected_output.get("requires_judge_review") is True)

    unknown_keys = sorted(set(expected_output) - _SUPPORTED_BELIEF_FIELDS)
    if unknown_keys:
        requires_judge_review = True
        errors.append(f"unsupported_expected_fields:{','.join(unknown_keys)}")

    if "min_belief" in expected_output:
        checks += 1
        if actual.belief >= float(expected_output["min_belief"]):
            passed_checks += 1
        else:
            errors.append("belief_below_min")

    if "max_belief" in expected_output:
        checks += 1
        if actual.belief <= float(expected_output["max_belief"]):
            passed_checks += 1
        else:
            errors.append("belief_above_max")

    if "min_confidence" in expected_output:
        checks += 1
        if actual.confidence >= float(expected_output["min_confidence"]):
            passed_checks += 1
        else:
            errors.append("confidence_below_min")

    if "rationale_contains" in expected_output:
        checks += 1
        expected_text = str(expected_output["rationale_contains"]).lower()
        if expected_text in actual.rationale.lower():
            passed_checks += 1
        else:
            errors.append("rationale_missing_substring")

    if "direction" in expected_output:
        direction = str(expected_output["direction"])
        if direction not in {"increase", "decrease", "unchanged"}:
            errors.append("invalid_expected_direction")
        elif context.prior_belief is None:
            requires_judge_review = True
            errors.append("ambiguous_direction_without_prior")
        else:
            checks += 1
            if direction == "increase" and actual.belief > context.prior_belief:
                passed_checks += 1
            elif direction == "decrease" and actual.belief < context.prior_belief:
                passed_checks += 1
            elif direction == "unchanged" and actual.belief == context.prior_belief:
                passed_checks += 1
            else:
                errors.append("direction_mismatch")

    if checks == 0:
        requires_judge_review = True
        score = 1.0
    else:
        score = passed_checks / checks

    return ComparatorResult(
        passed=passed_checks == checks,
        score=score,
        errors=errors,
        requires_judge_review=requires_judge_review,
    )
