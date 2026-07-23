"""Model-visible semantic validation for simulator reconstruction outputs."""

from __future__ import annotations

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    MemoryEvolutionSimReconstructionContext,
    SimSystemOutput,
    VisibleClaimCandidate,
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


def _required_selected_entity_ids(
    *,
    selected_claims: list[VisibleClaimCandidate],
    role_policy: str,
) -> set[str]:
    subjects = {claim.subject_entity_id for claim in selected_claims}
    objects = {
        claim.object_entity_id
        for claim in selected_claims
        if claim.object_entity_id is not None
    }
    if role_policy in {"subject", "active_graph_subjects"}:
        return subjects
    if role_policy == "object":
        return objects
    if role_policy in {"subject_and_object", "audit_graph_entities"}:
        return subjects | objects
    raise ValueError(f"unsupported selected entity role policy: {role_policy}")


def validate_visible_sim_output(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    output: SimSystemOutput,
) -> tuple[LLMValidationIssue, ...]:
    """Validate only relationships disclosed in the model-visible context."""

    contract = context.checkpoint.task_contract
    issues: list[LLMValidationIssue] = []
    if output.operation not in contract.allowed_operations:
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
    if contract.belief_ranking_policy == "required" and not output.belief_ranking_ids:
        issues.append(
            _issue(
                "belief_ranking_required",
                ("belief_ranking_ids",),
                "belief_ranking_ids is required by the visible task contract",
            )
        )
    if contract.belief_ranking_policy == "forbidden" and output.belief_ranking_ids:
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

    required_entities = _required_selected_entity_ids(
        selected_claims=selected_claims,
        role_policy=contract.selected_entity_role_policy,
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

    selected_subjects = {claim.subject_entity_id for claim in selected_claims}
    active_definitions = {
        claim.claim_id: claim
        for claim in context.visible_claims
        if claim.subject_entity_id in selected_subjects
        and claim.predicate_id == "entity_type"
        and claim.lifecycle_state == "active"
    }
    rejected_active_definitions = sorted(
        set(active_definitions) & set(output.rejected_claim_ids)
    )
    if rejected_active_definitions:
        issues.append(
            _issue(
                "selected_subject_definition_rejected",
                ("rejected_claim_ids",),
                "active definitions for selected subjects cannot be rejected: "
                f"{rejected_active_definitions}",
            )
        )
    if contract.definition_claim_placement == "selected_and_supporting_required":
        missing_selected_definitions = sorted(
            set(active_definitions) - set(output.selected_claim_ids)
        )
        missing_supporting_definitions = sorted(
            set(active_definitions) - set(output.supporting_claim_ids)
        )
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
        incorrectly_selected_definitions = sorted(
            set(active_definitions) & set(output.selected_claim_ids)
        )
        if incorrectly_selected_definitions:
            issues.append(
                _issue(
                    "optional_definition_selected",
                    ("selected_claim_ids",),
                    "optional definitions belong in context or support, not selected truth: "
                    f"{incorrectly_selected_definitions}",
                )
            )

    selected_rejected = sorted(
        set(output.selected_claim_ids) & set(output.rejected_claim_ids)
    )
    supporting_rejected = sorted(
        set(output.supporting_claim_ids) & set(output.rejected_claim_ids)
    )
    if selected_rejected:
        issues.append(
            _issue(
                "selected_rejected_claim_overlap",
                ("rejected_claim_ids",),
                f"selected claims cannot also be rejected: {selected_rejected}",
            )
        )
    if supporting_rejected:
        issues.append(
            _issue(
                "supporting_rejected_claim_overlap",
                ("rejected_claim_ids",),
                f"supporting claims cannot also be rejected: {supporting_rejected}",
            )
        )
    return tuple(issues)
