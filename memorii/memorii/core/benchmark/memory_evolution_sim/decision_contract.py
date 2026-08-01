"""Deterministic contract validation for simulator semantic decisions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from memorii.core.benchmark.memory_evolution_sim.claim_policy import (
    is_action_claim,
    is_execution_eligible_claim,
    is_noncurrent_claim,
)
from memorii.core.benchmark.memory_evolution_sim.definition_placement import (
    definition_placement_for_selected_claims,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimClaimSemanticRole,
    SimSemanticDecision,
)
from memorii.core.benchmark.task_conditioned_fields import (
    TaskFieldPresencePolicy,
    TaskFieldPresenceViolation,
    task_field_presence_violation,
    task_operation_allowed,
)


class SimDecisionContractViolationCode(StrEnum):
    INVALID_CLAIM_ID = "invalid_claim_id"
    MISSING_CLAIM_ASSESSMENT = "missing_claim_assessment"
    DUPLICATE_CLAIM_ASSESSMENT = "duplicate_claim_assessment"
    INVALID_UNCERTAIN_ID = "invalid_uncertain_id"
    OPERATION_NOT_ALLOWED = "operation_not_allowed"
    EMPTY_PRIMARY_SELECTION = "empty_primary_selection"
    STALE_SELECTED_CLAIM = "stale_selected_claim"
    NON_ACTION_SELECTED_FOR_EXECUTION = "non_action_selected_for_execution"
    INACTIVE_ACTION_SELECTED_FOR_EXECUTION = "inactive_action_selected_for_execution"
    BELIEF_RANKING_REQUIRED = "belief_ranking_required"
    BELIEF_RANKING_FORBIDDEN = "belief_ranking_forbidden"
    BELIEF_RANKING_INVALID = "belief_ranking_invalid"
    OPTIONAL_DEFINITION_PRIMARY = "optional_definition_primary"


class SimDecisionContractIssue(BaseModel):
    code: SimDecisionContractViolationCode
    location: tuple[str | int, ...]
    offending_ids: tuple[str, ...] = ()
    allowed_values: tuple[str, ...] = ()
    message: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True)


class SimDecisionContractValidation(BaseModel):
    issues: tuple[SimDecisionContractIssue, ...]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_sim_decision_contract(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    semantic: SimSemanticDecision,
) -> SimDecisionContractValidation:
    """Validate mechanically knowable decision constraints without an oracle."""

    claims = {claim.claim_id: claim for claim in context.visible_claims}
    visible_claim_ids = set(claims)
    assessment_ids = [assessment.claim_id for assessment in semantic.claim_assessments]
    assessment_id_set = set(assessment_ids)
    assessment_counts = Counter(assessment_ids)
    primary_ids = [
        assessment.claim_id
        for assessment in semantic.claim_assessments
        if assessment.role == SimClaimSemanticRole.PRIMARY
    ]
    ranked = [
        assessment
        for assessment in semantic.claim_assessments
        if assessment.belief_rank is not None
    ]
    all_visible_ids = (
        visible_claim_ids
        | set(context.visible_relation_ids)
        | set(context.visible_entity_ids)
        | {event.event_id for event in context.visible_events}
    )
    issues: list[SimDecisionContractIssue] = []

    invalid_claim_ids = sorted(assessment_id_set - visible_claim_ids)
    if invalid_claim_ids:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.INVALID_CLAIM_ID,
                ("claim_assessments",),
                offending_ids=invalid_claim_ids,
                allowed_values=sorted(visible_claim_ids),
                message="claim assessments may reference only visible claim IDs",
            )
        )
    missing_claim_ids = sorted(visible_claim_ids - assessment_id_set)
    if missing_claim_ids:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.MISSING_CLAIM_ASSESSMENT,
                ("claim_assessments",),
                offending_ids=missing_claim_ids,
                message="every visible claim requires exactly one assessment",
            )
        )
    duplicate_claim_ids = sorted(
        claim_id for claim_id, count in assessment_counts.items() if count > 1
    )
    if duplicate_claim_ids:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.DUPLICATE_CLAIM_ASSESSMENT,
                ("claim_assessments",),
                offending_ids=duplicate_claim_ids,
                message="visible claims may be assessed only once",
            )
        )
    invalid_uncertain_ids = sorted(set(semantic.uncertain_ids) - all_visible_ids)
    if invalid_uncertain_ids:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.INVALID_UNCERTAIN_ID,
                ("uncertain_ids",),
                offending_ids=invalid_uncertain_ids,
                allowed_values=sorted(all_visible_ids),
                message="uncertainty may reference only visible IDs",
            )
        )
    if not task_operation_allowed(
        allowed_operations=context.checkpoint.task_contract.allowed_operations,
        operation=semantic.operation,
    ):
        issues.append(
            _issue(
                SimDecisionContractViolationCode.OPERATION_NOT_ALLOWED,
                ("operation",),
                allowed_values=context.checkpoint.task_contract.allowed_operations,
                message="operation is not permitted by the visible task contract",
            )
        )
    if semantic.operation != "abstain" and not primary_ids:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.EMPTY_PRIMARY_SELECTION,
                ("claim_assessments",),
                allowed_values=(SimClaimSemanticRole.PRIMARY.value,),
                message="non-abstaining decisions require a primary claim",
            )
        )

    visible_primary_ids = [claim_id for claim_id in primary_ids if claim_id in claims]
    definition_placement = definition_placement_for_selected_claims(
        context=context,
        selected_claim_ids=visible_primary_ids,
    )
    if definition_placement.channel == "context":
        optional_primary_ids = sorted(
            set(definition_placement.claim_ids) & set(visible_primary_ids)
        )
        if optional_primary_ids:
            issues.append(
                _issue(
                    SimDecisionContractViolationCode.OPTIONAL_DEFINITION_PRIMARY,
                    ("claim_assessments",),
                    offending_ids=optional_primary_ids,
                    allowed_values=(SimClaimSemanticRole.RELEVANT.value,),
                    message="context-only definitions cannot be primary claims",
                )
            )
    if not context.checkpoint.task_contract.allow_stale_selected_claims:
        stale_primary_ids = sorted(
            claim_id
            for claim_id in visible_primary_ids
            if is_noncurrent_claim(claims[claim_id])
        )
        if stale_primary_ids:
            issues.append(
                _issue(
                    SimDecisionContractViolationCode.STALE_SELECTED_CLAIM,
                    ("claim_assessments",),
                    offending_ids=stale_primary_ids,
                    allowed_values=("active",),
                    message="the task contract forbids noncurrent primary claims",
                )
            )
    if semantic.operation == "next_action":
        non_action_ids = sorted(
            claim_id
            for claim_id in visible_primary_ids
            if not is_action_claim(claims[claim_id])
        )
        if non_action_ids:
            issues.append(
                _issue(
                    SimDecisionContractViolationCode.NON_ACTION_SELECTED_FOR_EXECUTION,
                    ("claim_assessments",),
                    offending_ids=non_action_ids,
                    allowed_values=("active_action_claim",),
                    message="next_action primary claims must describe action state",
                )
            )
        inactive_action_ids = sorted(
            claim_id
            for claim_id in visible_primary_ids
            if is_action_claim(claims[claim_id])
            and not is_execution_eligible_claim(claims[claim_id])
        )
        if inactive_action_ids:
            issues.append(
                _issue(
                    SimDecisionContractViolationCode.INACTIVE_ACTION_SELECTED_FOR_EXECUTION,
                    ("claim_assessments",),
                    offending_ids=inactive_action_ids,
                    allowed_values=("active_nonterminal_action",),
                    message="next_action primary claims must be active and nonterminal",
                )
            )

    ranking_presence = task_field_presence_violation(
        policy=TaskFieldPresencePolicy(
            context.checkpoint.task_contract.belief_ranking_policy
        ),
        item_count=len(ranked),
    )
    if ranking_presence == TaskFieldPresenceViolation.REQUIRED_MISSING:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.BELIEF_RANKING_REQUIRED,
                ("claim_assessments",),
                message="the task contract requires a belief ranking",
            )
        )
    elif ranking_presence == TaskFieldPresenceViolation.FORBIDDEN_PRESENT:
        issues.append(
            _issue(
                SimDecisionContractViolationCode.BELIEF_RANKING_FORBIDDEN,
                ("claim_assessments",),
                offending_ids=sorted(
                    assessment.claim_id for assessment in ranked
                ),
                allowed_values=("null",),
                message="the task contract forbids belief ranks",
            )
        )
    ranks = [assessment.belief_rank for assessment in ranked]
    if ranked and (
        any(
            assessment.role == SimClaimSemanticRole.IRRELEVANT
            for assessment in ranked
        )
        or len(ranks) != len(set(ranks))
        or set(ranks) != set(range(1, len(ranks) + 1))
    ):
        issues.append(
            _issue(
                SimDecisionContractViolationCode.BELIEF_RANKING_INVALID,
                ("claim_assessments",),
                offending_ids=sorted(
                    assessment.claim_id for assessment in ranked
                ),
                message="belief ranks must be unique, contiguous, and relevant",
            )
        )
    return SimDecisionContractValidation(issues=tuple(issues))


def _issue(
    code: SimDecisionContractViolationCode,
    location: tuple[str | int, ...],
    *,
    offending_ids: Sequence[str] = (),
    allowed_values: Sequence[str] = (),
    message: str,
) -> SimDecisionContractIssue:
    return SimDecisionContractIssue(
        code=code,
        location=location,
        offending_ids=tuple(offending_ids),
        allowed_values=tuple(allowed_values),
        message=message,
    )
