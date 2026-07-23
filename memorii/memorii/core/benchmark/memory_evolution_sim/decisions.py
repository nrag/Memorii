"""Simulator expected, rule, and provider decision adapters."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_sim.output_validation import sim_output_allowed_id_errors
from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentGraphScenario,
    MemoryEvolutionSimReconstructionContext,
    OracleCheckpoint,
    SimSystemOutput,
    SurfaceObservation,
)
from memorii.core.benchmark.memory_evolution_sim.utils import extract_rule_answer, normalize_sim_text, ordered_unique
from memorii.core.llm_decision.models import LLMDecisionMode, LLMDecisionPoint, LLMDecisionStatus, LLMDecisionTrace
from memorii.core.llm_provider.models import LLMDecisionResult, LLMStructuredRequest, LLMStructuredResponse
from memorii.core.llm_trace.builder import build_llm_decision_trace_from_result


def expected_sim_output_for_checkpoint(checkpoint: OracleCheckpoint) -> SimSystemOutput:
    operation: Literal["answer", "next_action", "graph_reconstruction", "abstain"]
    if checkpoint.expected_abstention:
        operation = "abstain"
    elif checkpoint.expected_next_action is not None:
        operation = "next_action"
    elif "graph_reconstruction" in checkpoint.task_contract.allowed_operations:
        operation = "graph_reconstruction"
    else:
        operation = "answer"
    execution = checkpoint.checkpoint_type == "execution_continuation"
    selected_claim_ids = list(checkpoint.expected_execution_claim_ids if execution else checkpoint.expected_claim_ids)
    selected_entity_ids = list(
        checkpoint.expected_execution_entity_ids if execution else checkpoint.expected_entity_ids
    )
    citations = list(
        checkpoint.expected_execution_citation_event_ids if execution else checkpoint.expected_citation_event_ids
    )
    graph_checkpoint = checkpoint.checkpoint_type in {
        "entity_reconstruction",
        "entity_split_repair",
        "claim_rekey",
        "conflict_audit",
    }
    context_claim_ids = list(checkpoint.expected_excluded_claim_ids) if graph_checkpoint else []
    context_entity_ids = list(checkpoint.expected_excluded_entity_ids) if graph_checkpoint else []
    selected_relation_ids = list(checkpoint.expected_relation_ids)
    supporting_relation_ids = list(checkpoint.expected_relation_ids)
    context_relation_ids = list(checkpoint.expected_relation_ids) if graph_checkpoint else []
    if checkpoint.checkpoint_type == "source_trust_conflict":
        selected_relation_ids = []
        supporting_relation_ids = []
        context_relation_ids = ordered_unique([*context_relation_ids, *checkpoint.expected_relation_ids])
    return SimSystemOutput(
        operation=operation,
        belief_ranking_ids=(
            list(checkpoint.expected_claim_ids) if checkpoint.checkpoint_type == "belief_ranking" else []
        ),
        selected_entity_ids=selected_entity_ids,
        selected_claim_ids=selected_claim_ids,
        selected_relation_ids=selected_relation_ids,
        supporting_claim_ids=list(selected_claim_ids),
        supporting_relation_ids=supporting_relation_ids,
        supporting_citation_event_ids=citations,
        rejected_entity_ids=list(checkpoint.expected_excluded_entity_ids),
        rejected_claim_ids=list(checkpoint.expected_excluded_claim_ids),
        context_entity_ids=context_entity_ids,
        context_claim_ids=context_claim_ids,
        context_relation_ids=context_relation_ids,
        answer=checkpoint.expected_answer,
        next_action=checkpoint.expected_next_action,
        uncertain_ids=list(checkpoint.expected_uncertain_ids),
        confidence=0.35 if checkpoint.expected_abstention else 0.92,
        rationale="oracle-shaped dry-run graph reconstruction",
    )


def fake_llm_result_for_memory_evolution_sim(
    *, request: LLMStructuredRequest, decision: SimSystemOutput, provider_name: str = "fake"
) -> LLMDecisionResult:
    output = decision.model_dump(mode="json")
    response = LLMStructuredResponse(
        request_id=request.request_id,
        provider=provider_name,
        requested_model=request.model_defaults.model,
        actual_model=request.model_defaults.model,
        raw_text=json.dumps(output, sort_keys=True),
        parsed_json=output,
        valid_json=True,
        schema_valid=True,
    )
    return LLMDecisionResult(request=request, response=response, output=output, success=True)


def memory_evolution_sim_trace_for_rule(
    *, context: MemoryEvolutionSimReconstructionContext, decision: SimSystemOutput, mode: str
) -> LLMDecisionTrace:
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
    output = decision.model_dump(mode="json")
    id_errors = sim_output_allowed_id_errors(scenario=scenario, output=decision)
    status = LLMDecisionStatus.VALIDATION_FAILED if id_errors else LLMDecisionStatus.SUCCEEDED
    trace = build_llm_decision_trace_from_result(
        decision_point=LLMDecisionPoint.MEMORY_EVOLUTION_SIM_RECONSTRUCTION,
        mode=mode,
        result=result,
        final_output=output,
        fallback_used=False,
        status=status,
    )
    if id_errors:
        trace.validation_errors.extend(id_errors)
        return output, trace, False, "llm_output_referenced_invalid_ids"
    return output, trace, True, None


def rule_sim_output_for_checkpoint(*, scenario: LatentGraphScenario, checkpoint: OracleCheckpoint) -> SimSystemOutput:
    tokens = set(normalize_sim_text(checkpoint.query_or_task).split())
    candidates = [event for event in scenario.observations if event.modality != "noise"]
    historical = bool(tokens & {"january", "historical", "before", "previously", "earlier"})
    owner_intent = bool(tokens & {"owner", "owns", "owned", "ownership"})
    continuation_intent = bool(tokens & {"branch", "continue", "continuation", "next", "resume"})
    belief_ranking_intent = bool(tokens & {"belief", "beliefs", "rank", "ranking"})

    def owner_score(event: SurfaceObservation) -> int:
        event_tokens = set(normalize_sim_text(event.text).split())
        return int(owner_intent and bool(event_tokens & {"owner", "owns", "owned", "ownership"}))

    ranked = sorted(
        candidates,
        key=lambda event: (
            -owner_score(event),
            -len(tokens & set(normalize_sim_text(event.text).split())),
            event.timestamp.timestamp() if historical else -event.timestamp.timestamp(),
            -event.trust_level,
            event.event_id,
        ),
    )
    selected = ranked[0] if ranked else None
    return SimSystemOutput(
        operation="next_action" if continuation_intent else "answer",
        belief_ranking_ids=(list(selected.exposed_claim_ids) if selected and belief_ranking_intent else []),
        selected_entity_ids=list(selected.exposed_entity_ids if selected else []),
        selected_claim_ids=list(selected.exposed_claim_ids if selected else []),
        selected_relation_ids=list(selected.exposed_relation_ids if selected else []),
        supporting_claim_ids=list(selected.exposed_claim_ids if selected else []),
        supporting_relation_ids=list(selected.exposed_relation_ids if selected else []),
        supporting_citation_event_ids=[selected.event_id] if selected else [],
        answer=extract_rule_answer(selected.text) if selected else None,
        next_action=f"continue {selected.event_id}" if selected and continuation_intent else None,
        confidence=0.45,
        rationale="shallow lexical/recency reconstruction baseline",
    )
