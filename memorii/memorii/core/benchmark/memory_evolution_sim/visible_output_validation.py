"""Model-visible semantic validation for simulator reconstruction outputs."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.channel_contract import (
    channel_algebra_violations,
    selected_entity_ids_for_claims,
)
from memorii.core.benchmark.memory_evolution_sim.definition_placement import (
    definition_placement_for_selected_claims,
)
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimSystemOutput,
    VisibleClaimCandidate,
)
from memorii.core.benchmark.task_conditioned_fields import (
    TaskFieldPresencePolicy,
    TaskFieldPresenceViolation,
    task_field_presence_violation,
    task_operation_allowed,
)
from memorii.core.llm_validation import (
    LLMValidationIssue,
    LLMValidationStage,
)


def _issue(
    code: str,
    location: tuple[str | int, ...],
    message: str,
) -> LLMValidationIssue:
    return LLMValidationIssue(
        stage=LLMValidationStage.SEMANTIC,
        code=code,
        location=location,
        message=message,
    )


def validate_visible_sim_output(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    output: SimSystemOutput,
) -> tuple[LLMValidationIssue, ...]:
    """Validate only relationships disclosed in the model-visible context."""

    contract = context.checkpoint.task_contract
    issues: list[LLMValidationIssue] = []
    if not task_operation_allowed(
        allowed_operations=contract.allowed_operations,
        operation=output.operation,
    ):
        issues.append(
            _issue(
                "operation_not_allowed",
                ("operation",),
                "operation is not allowed by the visible task contract",
            )
        )
    if contract.answer_required and output.operation == "answer" and not output.answer:
        issues.append(
            _issue(
                "answer_required",
                ("answer",),
                "answer is required by the visible task contract",
            )
        )
    if contract.requires_next_action and not output.next_action:
        issues.append(
            _issue(
                "next_action_required",
                ("next_action",),
                "next_action is required by the visible task contract",
            )
        )
    ranking_presence = task_field_presence_violation(
        policy=TaskFieldPresencePolicy(contract.belief_ranking_policy),
        item_count=len(output.belief_ranking_ids),
    )
    if ranking_presence == TaskFieldPresenceViolation.REQUIRED_MISSING:
        issues.append(
            _issue(
                "belief_ranking_required",
                ("belief_ranking_ids",),
                "belief_ranking_ids is required by the visible task contract",
            )
        )
    elif ranking_presence == TaskFieldPresenceViolation.FORBIDDEN_PRESENT:
        issues.append(
            _issue(
                "belief_ranking_forbidden",
                ("belief_ranking_ids",),
                "belief_ranking_ids must be empty for this task",
            )
        )

    claim_by_id = {claim.claim_id: claim for claim in context.visible_claims}
    selected_claims: list[VisibleClaimCandidate] = []
    for index, claim_id in enumerate(output.selected_claim_ids):
        claim = claim_by_id.get(claim_id)
        if claim is None:
            issues.append(
                _issue(
                    "selected_claim_not_visible",
                    ("selected_claim_ids", index),
                    "selected claim does not have a visible candidate card",
                )
            )
        else:
            selected_claims.append(claim)

    required_entities = set(
        selected_entity_ids_for_claims(
            selected_claims=selected_claims,
            role_policy=contract.selected_entity_role_policy,
        )
    )
    missing_entities = sorted(required_entities - set(output.selected_entity_ids))
    if missing_entities:
        issues.append(
            _issue(
                "selected_entity_role_mismatch",
                ("selected_entity_ids",),
                f"selected entities are missing required claim endpoints: {missing_entities}",
            )
        )

    missing_support = sorted(set(output.selected_claim_ids) - set(output.supporting_claim_ids))
    if missing_support:
        issues.append(
            _issue(
                "selected_claim_missing_support",
                ("supporting_claim_ids",),
                f"selected claims must also be supporting: {missing_support}",
            )
        )
    supporting_citations = set(output.supporting_citation_event_ids)
    for claim in selected_claims:
        if not supporting_citations.intersection(claim.evidence_event_ids):
            issues.append(
                _issue(
                    "selected_claim_missing_direct_citation",
                    ("supporting_citation_event_ids",),
                    f"selected claim lacks a direct visible citation: {claim.claim_id}",
                )
            )

    definition_placement = definition_placement_for_selected_claims(
        context=context,
        selected_claim_ids=output.selected_claim_ids,
    )
    active_definition_ids = set(definition_placement.claim_ids)
    rejected_active_definitions = sorted(active_definition_ids & set(output.rejected_claim_ids))
    if rejected_active_definitions:
        issues.append(
            _issue(
                "selected_subject_definition_rejected",
                ("rejected_claim_ids",),
                f"active definitions for selected subjects cannot be rejected: {rejected_active_definitions}",
            )
        )
    if definition_placement.channel == "selected_and_supporting":
        missing_selected_definitions = sorted(active_definition_ids - set(output.selected_claim_ids))
        missing_supporting_definitions = sorted(active_definition_ids - set(output.supporting_claim_ids))
        if missing_selected_definitions:
            issues.append(
                _issue(
                    "required_definition_not_selected",
                    ("selected_claim_ids",),
                    f"required active definitions are not selected: {missing_selected_definitions}",
                )
            )
        if missing_supporting_definitions:
            issues.append(
                _issue(
                    "required_definition_not_supporting",
                    ("supporting_claim_ids",),
                    f"required active definitions are not supporting: {missing_supporting_definitions}",
                )
            )
    else:
        incorrectly_selected_definitions = sorted(active_definition_ids & set(output.selected_claim_ids))
        if incorrectly_selected_definitions:
            issues.append(
                _issue(
                    "optional_definition_selected",
                    ("selected_claim_ids",),
                    "optional definitions belong in context or support, not selected truth: "
                    f"{incorrectly_selected_definitions}",
                )
            )

    for violation in channel_algebra_violations(output):
        issues.append(
            _issue(
                violation.value,
                (),
                f"compiled channel algebra violation: {violation.value}",
            )
        )
    return tuple(issues)
