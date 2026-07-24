from __future__ import annotations

from typing import Literal

from memorii.core.benchmark.memory_evolution_sim import (
    SimClaimSemanticRole,
    SimDecisionContractViolationCode,
    sim_reconstruction_context_for_checkpoint,
    validate_sim_decision_contract,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    generate_scenario_by_family,
    oracle_shaped_sim_semantic_decision,
)


def _case(
    *,
    family: str,
    checkpoint_type: str,
    profile: Literal["smoke", "adversarial", "long_horizon"] = "adversarial",
):
    scenario = generate_scenario_by_family(
        profile=profile,
        family=family,
        seed=7,
        noise_rate=0.35,
    )
    checkpoint = checkpoint_by_type(scenario, checkpoint_type)
    context = sim_reconstruction_context_for_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
    )
    semantic = oracle_shaped_sim_semantic_decision(
        context=context,
        checkpoint=checkpoint,
    )
    return context, semantic


def test_valid_decision_has_no_contract_issues() -> None:
    context, semantic = _case(
        family="current_vs_historical_truth",
        checkpoint_type="current_truth",
    )

    result = validate_sim_decision_contract(context=context, semantic=semantic)

    assert result.valid
    assert result.issues == ()


def test_contract_reports_localized_invalid_and_missing_claim_ids() -> None:
    context, semantic = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
    )
    replaced_id = semantic.claim_assessments[0].claim_id
    changed = semantic.model_copy(
        update={
            "claim_assessments": [
                semantic.claim_assessments[0].model_copy(
                    update={"claim_id": "claim:not-visible"}
                ),
                *semantic.claim_assessments[1:],
            ],
            "uncertain_ids": ["entity:not-visible"],
        }
    )

    result = validate_sim_decision_contract(context=context, semantic=changed)
    issues = {issue.code: issue for issue in result.issues}

    assert issues[
        SimDecisionContractViolationCode.INVALID_CLAIM_ID
    ].offending_ids == ("claim:not-visible",)
    assert issues[
        SimDecisionContractViolationCode.MISSING_CLAIM_ASSESSMENT
    ].offending_ids == (replaced_id,)
    assert issues[
        SimDecisionContractViolationCode.INVALID_UNCERTAIN_ID
    ].offending_ids == ("entity:not-visible",)
    assert all(issue.location for issue in result.issues)
    assert all(issue.message for issue in result.issues)


def test_contract_reports_duplicate_claim_once_with_exact_id() -> None:
    context, semantic = _case(
        family="entity_split",
        checkpoint_type="entity_split_repair",
    )
    duplicate_id = semantic.claim_assessments[0].claim_id
    changed = semantic.model_copy(
        update={
            "claim_assessments": [
                *semantic.claim_assessments,
                semantic.claim_assessments[0],
            ]
        }
    )

    result = validate_sim_decision_contract(context=context, semantic=changed)
    issue = next(
        issue
        for issue in result.issues
        if issue.code
        == SimDecisionContractViolationCode.DUPLICATE_CLAIM_ASSESSMENT
    )

    assert issue.location == ("claim_assessments",)
    assert issue.offending_ids == (duplicate_id,)


def test_execution_contract_distinguishes_non_action_and_inactive_action() -> None:
    context, semantic = _case(
        family="abandoned_then_resumed_work",
        checkpoint_type="execution_continuation",
        profile="long_horizon",
    )
    ownership = next(
        claim
        for claim in context.visible_claims
        if claim.predicate_id not in {"action_state", "status", "progress"}
        and "action" not in claim.predicate_id
    )
    blocked = next(
        claim
        for claim in context.visible_claims
        if claim.object_value.casefold() == "blocked"
    )

    def with_primary(claim_id: str):
        return semantic.model_copy(
            update={
                "claim_assessments": [
                    assessment.model_copy(
                        update={
                            "role": (
                                SimClaimSemanticRole.PRIMARY
                                if assessment.claim_id == claim_id
                                else SimClaimSemanticRole.IRRELEVANT
                            )
                        }
                    )
                    for assessment in semantic.claim_assessments
                ]
            }
        )

    ownership_result = validate_sim_decision_contract(
        context=context,
        semantic=with_primary(ownership.claim_id),
    )
    blocked_result = validate_sim_decision_contract(
        context=context,
        semantic=with_primary(blocked.claim_id),
    )

    ownership_issue = next(
        issue
        for issue in ownership_result.issues
        if issue.code
        == SimDecisionContractViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION
    )
    blocked_issue = next(
        issue
        for issue in blocked_result.issues
        if issue.code
        == SimDecisionContractViolationCode.INACTIVE_ACTION_SELECTED_FOR_EXECUTION
    )
    assert ownership_issue.offending_ids == (ownership.claim_id,)
    assert ownership_issue.allowed_values == ("active_action_claim",)
    assert blocked_issue.offending_ids == (blocked.claim_id,)
    assert blocked_issue.allowed_values == ("active_nonterminal_action",)
