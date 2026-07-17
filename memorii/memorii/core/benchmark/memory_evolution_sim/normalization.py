"""Role-aware simulator output normalization and decision adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_sim.diagnostics import sim_output_allowed_id_errors
from memorii.core.benchmark.memory_evolution_sim.judge_features import required_selected_entity_ids_for_policy
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    ObservabilityLabel,
    OracleCheckpoint,
    SimOutputNormalization,
    SimSystemOutput,
    SurfaceObservation,
)
from memorii.core.benchmark.memory_evolution_sim.utils import (
    _claim_by_id,
    _extract_rule_answer,
    _is_visible_claim,
    _norm,
    _ordered_unique,
    _required_definition_claim_ids_for_selected_claims,
)
from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


def expected_sim_output_for_checkpoint(checkpoint: OracleCheckpoint) -> SimSystemOutput:
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"]
    if checkpoint.expected_abstention:
        operation = "abstain"
    elif checkpoint.expected_next_action is not None:
        operation = "next_action"
    else:
        graph_allowed = "graph_reconstruction" in checkpoint.checkpoint_contract.allowed_operations
        operation = "graph_reconstruction" if graph_allowed else "answer"
    rejected_claim_ids = list(checkpoint.expected_excluded_claim_ids)
    rejected_entity_ids = list(checkpoint.expected_excluded_entity_ids)
    rejected_relation_ids: list[str] = []
    context_claim_ids: list[str] = []
    context_entity_ids: list[str] = []
    context_relation_ids: list[str] = []
    if checkpoint.checkpoint_type in {"entity_reconstruction", "entity_split_repair", "claim_rekey", "conflict_audit"}:
        context_claim_ids = list(rejected_claim_ids)
        context_entity_ids = list(rejected_entity_ids)
        context_relation_ids = list(checkpoint.expected_relation_ids)
    selected_claim_ids = list(
        checkpoint.expected_execution_claim_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_claim_ids
    )
    selected_entity_ids = list(
        checkpoint.expected_execution_entity_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_entity_ids
    )
    selected_relation_ids = list(checkpoint.expected_relation_ids)
    supporting_claim_ids = list(selected_claim_ids)
    supporting_relation_ids = list(checkpoint.expected_relation_ids)
    if checkpoint.checkpoint_type == "source_trust_conflict":
        selected_relation_ids = []
        supporting_relation_ids = []
        context_relation_ids = _ordered_unique([*context_relation_ids, *checkpoint.expected_relation_ids])
    supporting_citation_event_ids = list(
        checkpoint.expected_execution_citation_event_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_citation_event_ids
    )
    return SimSystemOutput(
        operation=operation,
        entity_ids=_ordered_unique([*selected_entity_ids, *context_entity_ids, *rejected_entity_ids]),
        claim_ids=_ordered_unique([*selected_claim_ids, *supporting_claim_ids, *context_claim_ids, *rejected_claim_ids]),
        relation_ids=_ordered_unique([*selected_relation_ids, *supporting_relation_ids, *context_relation_ids, *rejected_relation_ids]),
        citation_event_ids=list(supporting_citation_event_ids),
        belief_ranking_ids=list(checkpoint.expected_claim_ids) if checkpoint.checkpoint_type == "belief_ranking" else [],
        selected_entity_ids=selected_entity_ids,
        selected_claim_ids=selected_claim_ids,
        selected_relation_ids=selected_relation_ids,
        supporting_claim_ids=supporting_claim_ids,
        supporting_relation_ids=supporting_relation_ids,
        supporting_citation_event_ids=supporting_citation_event_ids,
        rejected_entity_ids=rejected_entity_ids,
        rejected_claim_ids=rejected_claim_ids,
        rejected_relation_ids=rejected_relation_ids,
        rejection_citation_event_ids=[],
        context_entity_ids=context_entity_ids,
        context_claim_ids=context_claim_ids,
        context_relation_ids=context_relation_ids,
        context_citation_event_ids=[],
        answer=checkpoint.expected_answer,
        next_action=checkpoint.expected_next_action,
        uncertain_ids=list(checkpoint.expected_uncertain_ids),
        confidence=0.92 if not checkpoint.expected_abstention else 0.35,
        rationale="oracle-shaped dry-run graph reconstruction",
    )

def normalize_sim_system_output_for_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    output: SimSystemOutput,
) -> tuple[SimSystemOutput, SimOutputNormalization]:
    """Complete safe role-aware graph channels using visible scenario candidates.

    The normalizer repairs deterministic channel omissions, but intentionally does
    not remove selected/supporting pollution. Wrong-entity or stale evidence in
    supporting_* must still fail precision judges. A definition claim that this
    normalizer promotes is the one exception: it cannot remain rejected because
    that would create an internally contradictory role assignment.
    """

    selected_entity_ids = list(output.selected_entity_ids)
    selected_claim_ids = list(output.selected_claim_ids)
    supporting_claim_ids = list(output.supporting_claim_ids)
    supporting_citation_event_ids = list(output.supporting_citation_event_ids)
    rejected_entity_ids = list(output.rejected_entity_ids)
    rejected_claim_ids = list(output.rejected_claim_ids)
    rejection_citation_event_ids = list(output.rejection_citation_event_ids)
    context_entity_ids = list(output.context_entity_ids)
    context_relation_ids = list(output.context_relation_ids)

    auto_selected_entities: list[str] = []
    auto_rejected_entities: list[str] = []
    auto_context_entities: list[str] = []
    auto_selected_claims: list[str] = []
    auto_supporting_claims: list[str] = []
    auto_supporting_events: list[str] = []
    auto_demoted_execution_context_claims: list[str] = []
    repaired_definition_claim_conflicts: list[str] = []
    auto_rejected_claims: list[str] = []
    auto_context_relations: list[str] = []
    reason_codes: list[str] = []

    def add_once(items: list[str], item: str, added: list[str], reason: str | None = None) -> None:
        if item not in items:
            items.append(item)
            added.append(item)
            if reason is not None:
                reason_codes.append(reason)

    visible_entities = {
        entity.entity_id for entity in scenario.entities if entity.observability != ObservabilityLabel.HIDDEN
    }
    visible_claims = {
        claim.claim_id
        for claim in scenario.claims
        if claim.observability != ObservabilityLabel.HIDDEN and _is_visible_claim(scenario, claim.claim_id)
    }
    visible_relations = {
        relation.relation_id
        for relation in scenario.relations
        if relation.observability != ObservabilityLabel.HIDDEN
        and any(relation.relation_id in observation.exposed_relation_ids for observation in scenario.observations)
    }
    selected_or_supporting_claims = set(selected_claim_ids) | set(supporting_claim_ids)

    # Negative modality-suppression answers still need the active current truth in
    # selected/supporting channels when the model only placed it in context.
    if checkpoint.checkpoint_type == "modality_suppression":
        for claim_id in checkpoint.expected_claim_ids:
            claim = _claim_by_id(scenario, claim_id)
            if claim is None or claim_id not in visible_claims:
                continue
            if claim_id in output.context_claim_ids and claim_id not in selected_or_supporting_claims:
                add_once(selected_claim_ids, claim_id, auto_selected_claims, "current_truth_promoted_from_context")
                add_once(supporting_claim_ids, claim_id, auto_supporting_claims, "current_truth_promoted_from_context")
                if claim.subject.entity_id in visible_entities:
                    add_once(selected_entity_ids, claim.subject.entity_id, auto_selected_entities, "current_truth_promoted_from_context")
                for event_id in claim.evidence.source_event_ids:
                    add_once(
                        supporting_citation_event_ids,
                        event_id,
                        auto_supporting_events,
                        "current_truth_promoted_from_context",
                    )

    # Graph reconstruction requires entity definition/type support for selected
    # role facts; complete it from visible definition claims.
    interim_for_definitions = output.model_copy(update={"selected_claim_ids": _ordered_unique(selected_claim_ids)})
    for claim_id in _required_definition_claim_ids_for_selected_claims(scenario, interim_for_definitions):
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim_id not in visible_claims:
            continue
        if claim_id in rejected_claim_ids:
            rejected_claim_ids.remove(claim_id)
            repaired_definition_claim_conflicts.append(claim_id)
            reason_codes.append("definition_claim_conflict_repaired")
        if claim_id not in selected_claim_ids:
            add_once(selected_claim_ids, claim_id, auto_selected_claims, "definition_claim_completed")
        if claim_id not in supporting_claim_ids:
            add_once(supporting_claim_ids, claim_id, auto_supporting_claims, "definition_claim_completed")
        for event_id in claim.evidence.source_event_ids:
            add_once(supporting_citation_event_ids, event_id, auto_supporting_events, "definition_claim_completed")

    # Execution support is intentionally narrower than general factual support.
    # A model may repeat an owner/project fact in both context and supporting
    # channels; demote that redundant overlap, but keep uncontextualized support
    # pollution visible to the precision judge.
    if checkpoint.checkpoint_type == "execution_continuation":
        context_claim_ids = set(output.context_claim_ids)
        demoted_claim_ids = {
            claim_id
            for claim_id in supporting_claim_ids
            if claim_id in context_claim_ids
            and (claim := _claim_by_id(scenario, claim_id)) is not None
            and claim.claim_kind != "action_state"
        }
        if demoted_claim_ids:
            demoted_claim_ids_ordered = [
                claim_id for claim_id in supporting_claim_ids if claim_id in demoted_claim_ids
            ]
            supporting_claim_ids = [
                claim_id for claim_id in supporting_claim_ids if claim_id not in demoted_claim_ids
            ]
            auto_demoted_execution_context_claims.extend(demoted_claim_ids_ordered)
            retained_support_evidence_ids = {
                event_id
                for claim_id in [*selected_claim_ids, *supporting_claim_ids]
                if (claim := _claim_by_id(scenario, claim_id)) is not None
                for event_id in claim.evidence.source_event_ids
            }
            supporting_citation_event_ids = [
                event_id
                for event_id in supporting_citation_event_ids
                if event_id in retained_support_evidence_ids
            ]
            reason_codes.append("execution_context_support_demoted")

    if repaired_definition_claim_conflicts:
        remaining_rejected_evidence_ids = {
            event_id
            for claim_id in rejected_claim_ids
            if (claim := _claim_by_id(scenario, claim_id)) is not None
            for event_id in claim.evidence.source_event_ids
        }
        rejection_citation_event_ids = [
            event_id
            for event_id in rejection_citation_event_ids
            if event_id in remaining_rejected_evidence_ids
        ]

    # Explicit wrong-role traps should be rejected/contextualized when visible,
    # unless the model used them as selected/supporting truth. In that case the
    # precision judges must still fail.
    if checkpoint.checkpoint_type in {"entity_disambiguation", "entity_split_repair"}:
        selected_or_supporting_claims = set(selected_claim_ids) | set(supporting_claim_ids)
        for claim_id in checkpoint.expected_excluded_claim_ids:
            if claim_id not in visible_claims or claim_id in selected_or_supporting_claims:
                continue
            if claim_id not in rejected_claim_ids and claim_id not in output.context_claim_ids:
                add_once(rejected_claim_ids, claim_id, auto_rejected_claims, "visible_excluded_claim_rejected")

    selected_required_output = output.model_copy(update={"selected_claim_ids": _ordered_unique(selected_claim_ids)})
    selected_required = required_selected_entity_ids_for_policy(
        scenario=scenario,
        checkpoint=checkpoint,
        output=selected_required_output,
    )
    for entity_id in selected_required:
        if entity_id in visible_entities:
            add_once(selected_entity_ids, entity_id, auto_selected_entities, "selected_claim_subject_closed")

    for claim_id in rejected_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
            continue
        subject_entity_id = claim.subject.entity_id
        if subject_entity_id not in visible_entities:
            continue
        if subject_entity_id in selected_entity_ids:
            continue
        if subject_entity_id not in rejected_entity_ids and subject_entity_id not in context_entity_ids:
            add_once(rejected_entity_ids, subject_entity_id, auto_rejected_entities, "rejected_claim_subject_closed")

    for claim_id in output.context_claim_ids:
        claim = _claim_by_id(scenario, claim_id)
        if claim is None or claim.observability == ObservabilityLabel.HIDDEN:
            continue
        subject_entity_id = claim.subject.entity_id
        if subject_entity_id not in visible_entities:
            continue
        if subject_entity_id not in context_entity_ids:
            add_once(context_entity_ids, subject_entity_id, auto_context_entities, "context_claim_subject_closed")

    role_claim_ids = set(selected_claim_ids) | set(supporting_claim_ids) | set(rejected_claim_ids) | set(output.context_claim_ids)
    role_relation_ids = (
        set(output.selected_relation_ids)
        | set(output.supporting_relation_ids)
        | set(output.rejected_relation_ids)
        | set(context_relation_ids)
    )
    for relation in scenario.relations:
        if relation.relation_id not in visible_relations or relation.relation_id in role_relation_ids:
            continue
        if relation.relation_type not in {"contradicts", "corrects", "supersedes"}:
            continue
        if relation.source.endpoint_type != "claim" or relation.target.endpoint_type != "claim":
            continue
        if relation.source.endpoint_id in role_claim_ids and relation.target.endpoint_id in role_claim_ids:
            add_once(
                context_relation_ids,
                relation.relation_id,
                auto_context_relations,
                "visible_conflict_relation_closed_from_claim_channels",
            )

    normalized = output.model_copy(
        update={
            "selected_entity_ids": _ordered_unique(selected_entity_ids),
            "selected_claim_ids": _ordered_unique(selected_claim_ids),
            "supporting_claim_ids": _ordered_unique(supporting_claim_ids),
            "supporting_citation_event_ids": _ordered_unique(supporting_citation_event_ids),
            "rejected_entity_ids": _ordered_unique(rejected_entity_ids),
            "rejected_claim_ids": _ordered_unique(rejected_claim_ids),
            "rejection_citation_event_ids": _ordered_unique(rejection_citation_event_ids),
            "context_entity_ids": _ordered_unique(context_entity_ids),
            "context_relation_ids": _ordered_unique(context_relation_ids),
        }
    )
    normalized = SimSystemOutput.model_validate(normalized.model_dump(mode="json"))
    summary = SimOutputNormalization(
        normalization_applied=bool(
            auto_selected_entities
            or auto_rejected_entities
            or auto_context_entities
            or auto_selected_claims
            or auto_supporting_claims
            or auto_supporting_events
            or auto_demoted_execution_context_claims
            or repaired_definition_claim_conflicts
            or auto_rejected_claims
            or auto_context_relations
        ),
        auto_closed_selected_entity_ids=_ordered_unique(auto_selected_entities),
        auto_closed_rejected_entity_ids=_ordered_unique(auto_rejected_entities),
        auto_closed_context_entity_ids=_ordered_unique(auto_context_entities),
        auto_closed_context_relation_ids=_ordered_unique(auto_context_relations),
        auto_promoted_selected_claim_ids=_ordered_unique(auto_selected_claims),
        auto_promoted_supporting_claim_ids=_ordered_unique(auto_supporting_claims),
        auto_promoted_supporting_citation_event_ids=_ordered_unique(auto_supporting_events),
        auto_demoted_execution_context_claim_ids=_ordered_unique(auto_demoted_execution_context_claims),
        repaired_definition_claim_conflict_ids=_ordered_unique(repaired_definition_claim_conflicts),
        auto_rejected_claim_ids=_ordered_unique(auto_rejected_claims),
        normalization_reason_codes=_ordered_unique(reason_codes),
    )
    return normalized, summary

def fake_llm_result_for_memory_evolution_sim(
    *,
    request: LLMStructuredRequest,
    decision: SimSystemOutput,
    provider_name: str = "fake",
) -> LLMDecisionResult:
    import json

    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        model=request.model_defaults.model,
        raw_text=json.dumps(output, sort_keys=True),
        parsed_json=output,
        valid_json=True,
        schema_valid=True,
    )
    return LLMDecisionResult(request=request, response=response, output=output, success=True, failure_mode=None)

def memory_evolution_sim_trace_for_rule(
    *,
    context: MemoryEvolutionSimReconstructionContext,
    decision: SimSystemOutput,
    mode: str,
) -> LLMDecisionTrace:
    from uuid import uuid4

    return LLMDecisionTrace(
        trace_id=f"trace:sim-rule:{uuid4().hex}",
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
        mode=LLMDecisionMode(mode),
        input_payload=context.model_dump(mode="json"),
        parsed_output=decision.model_dump(mode="json"),
        final_output=decision.model_dump(mode="json"),
        status=LLMDecisionStatus.SUCCEEDED,
        created_at=datetime.now(UTC),
    )

def memory_evolution_sim_engine_result_from_llm(
    *,
    result: LLMDecisionResult,
    mode: LLMDecisionMode,
    scenario: LatentGraphScenario,
    rule_output: dict[str, object],
) -> tuple[dict[str, object], LLMDecisionTrace, bool, str | None]:
    if not result.success:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.PROVIDER_ERROR,
        )
        return rule_output, trace, False, result.failure_mode or "llm_decision_failed"
    try:
        decision = SimSystemOutput.model_validate(result.output)
    except ValidationError:
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
            mode=mode,
            result=result,
            final_output=rule_output,
            fallback_used=True,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        return rule_output, trace, False, "llm_decision_validation_failed"
    id_errors = sim_output_allowed_id_errors(scenario=scenario, output=decision)
    if id_errors:
        output = decision.model_dump(mode="json")
        trace = build_llm_decision_trace_from_result(
            decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
            mode=mode,
            result=result,
            final_output=output,
            fallback_used=False,
            status=LLMDecisionStatus.VALIDATION_FAILED,
        )
        trace.validation_errors.extend(id_errors)
        return output, trace, False, "llm_output_referenced_invalid_ids"
    output = decision.model_dump(mode="json")
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
        mode=mode,
        result=result,
        final_output=output,
        fallback_used=False,
        status=LLMDecisionStatus.SUCCEEDED,
    )
    return output, trace, True, None

def rule_sim_output_for_checkpoint(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
) -> SimSystemOutput:
    tokens = set(_norm(checkpoint.query_or_task).split())
    candidates = [event for event in scenario.observations if event.modality != "noise"]
    historical_intent = bool(tokens & {"january", "historical", "before", "previously", "earlier"})
    owner_intent = bool(tokens & {"owner", "owns", "owned", "ownership"})
    def owner_score(event: SurfaceObservation) -> int:
        event_tokens = set(_norm(event.text).split())
        return 1 if owner_intent and event_tokens & {"owner", "owns", "owned", "ownership"} else 0

    if historical_intent:
        ranked = sorted(
            candidates,
            key=lambda event: (
                -owner_score(event),
                -len(tokens & set(_norm(event.text).split())),
                event.timestamp.timestamp(),
                -event.trust_level,
                event.event_id,
            ),
        )
    else:
        ranked = sorted(
            candidates,
            key=lambda event: (
                -owner_score(event),
                -len(tokens & set(_norm(event.text).split())),
                -event.trust_level,
                -event.timestamp.timestamp(),
                event.event_id,
            ),
        )
    selected = ranked[0] if ranked else None
    return SimSystemOutput(
        operation="next_action" if checkpoint.expected_next_action else "answer",
        entity_ids=list(selected.exposed_entity_ids if selected else []),
        claim_ids=list(selected.exposed_claim_ids if selected else []),
        relation_ids=list(selected.exposed_relation_ids if selected else []),
        citation_event_ids=[selected.event_id] if selected else [],
        belief_ranking_ids=list(selected.exposed_claim_ids if selected and checkpoint.checkpoint_type == "belief_ranking" else []),
        selected_entity_ids=list(selected.exposed_entity_ids if selected else []),
        selected_claim_ids=list(selected.exposed_claim_ids if selected else []),
        selected_relation_ids=list(selected.exposed_relation_ids if selected else []),
        supporting_claim_ids=list(selected.exposed_claim_ids if selected else []),
        supporting_relation_ids=list(selected.exposed_relation_ids if selected else []),
        supporting_citation_event_ids=[selected.event_id] if selected else [],
        answer=_extract_rule_answer(selected.text) if selected else None,
        next_action=f"continue {selected.event_id}" if selected and checkpoint.expected_next_action else None,
        uncertain_ids=[],
        confidence=0.45,
        rationale="shallow lexical/recency reconstruction baseline",
    )
