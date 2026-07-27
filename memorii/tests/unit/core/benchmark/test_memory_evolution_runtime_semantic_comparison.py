from __future__ import annotations

import ast
import inspect

from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeActionGraphItemRow,
    RuntimeClaimGraphItemRow,
    RuntimeEntityGraphItemRow,
    RuntimeGraphItem,
)
from memorii.core.benchmark.memory_evolution_runtime.semantic_comparison import (
    compare_checkpoint_semantics,
)
from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios
from memorii.core.memory_evolution import ProductionRetrievalDecision


def _scenario_and_checkpoint():
    scenarios = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )
    scenario = next(item for item in scenarios if item.family == "current_vs_historical_truth")
    checkpoint = next(item for item in scenario.checkpoints if item.checkpoint_type == "current_truth")
    return scenario, checkpoint


def _runtime_view(
    *,
    reverse: bool = False,
    wrong_object: bool = False,
    opaque_entity_names: bool = False,
):
    scenario, checkpoint = _scenario_and_checkpoint()
    entities_by_id = {entity.entity_id: entity for entity in scenario.entities}
    claims_by_id = {claim.claim_id: claim for claim in scenario.claims}
    required_ids = [*checkpoint.expected_claim_ids, *checkpoint.expected_excluded_claim_ids]
    entity_runtime_id: dict[str, str] = {}
    items: list[RuntimeGraphItem] = []
    for claim_id in required_ids:
        claim = claims_by_id[claim_id]
        for entity_id in (claim.subject.entity_id, claim.object.entity_id):
            if not entity_id or entity_id in entity_runtime_id:
                continue
            entity = entities_by_id[entity_id]
            runtime_id = f"runtime:entity:{len(entity_runtime_id)}"
            entity_runtime_id[entity_id] = runtime_id
            items.append(
                RuntimeEntityGraphItemRow(
                    scenario_id="runtime-scenario",
                    runtime_item_id=runtime_id,
                    canonical_id=f"unrelated-id:{len(entity_runtime_id)}",
                    canonical_name=(
                        f"unrelated-id:{len(entity_runtime_id)}" if opaque_entity_names else entity.canonical_name
                    ),
                    entity_type=entity.entity_type,
                    aliases=[
                        entity.canonical_name,
                        *(alias.alias_text for alias in entity.aliases),
                    ],
                    lifecycle_state="active",
                    evidence_event_ids=[],
                )
            )
    runtime_claim_ids: dict[str, str] = {}
    for index, claim_id in enumerate(required_ids):
        claim = claims_by_id[claim_id]
        runtime_claim_id = f"runtime:claim:{index}"
        runtime_claim_ids[claim_id] = runtime_claim_id
        object_entity_id = entity_runtime_id.get(claim.object.entity_id or "", "")
        if wrong_object and claim_id in checkpoint.expected_claim_ids:
            object_entity_id = ""
        items.append(
            RuntimeClaimGraphItemRow(
                scenario_id="runtime-scenario",
                runtime_item_id=f"graph:{runtime_claim_id}",
                claim_id=runtime_claim_id,
                subject=claim.subject.canonical_name,
                subject_entity_id=entity_runtime_id[claim.subject.entity_id],
                predicate=claim.predicate.predicate_id,
                object=claim.object.value,
                object_entity_id=object_entity_id,
                object_value=(
                    "incorrect-value"
                    if wrong_object and claim_id in checkpoint.expected_claim_ids
                    else claim.object.normalized_value or claim.object.value
                ),
                scope=claim.scope.scope_key,
                valid_from=(claim.lifecycle.valid_from.isoformat() if claim.lifecycle.valid_from else ""),
                valid_to=(claim.lifecycle.valid_to.isoformat() if claim.lifecycle.valid_to else ""),
                lifecycle_state=claim.lifecycle.state.value,
                evidence_event_ids=list(claim.evidence.source_event_ids),
            )
        )
    if reverse:
        items.reverse()
    decision = ProductionRetrievalDecision(
        query=checkpoint.query_or_task,
        semantic_frame_status="matched",
        temporal_frame={},
        selected_record_ids=[runtime_claim_ids[claim_id] for claim_id in checkpoint.expected_claim_ids],
        supporting_record_ids=[runtime_claim_ids[claim_id] for claim_id in checkpoint.expected_claim_ids],
        context_record_ids=[],
        rejected_record_ids=[runtime_claim_ids[claim_id] for claim_id in checkpoint.expected_excluded_claim_ids],
    )
    return scenario, checkpoint, items, decision


def test_canonical_comparison_ignores_runtime_ids_and_traversal_order() -> None:
    scenario, checkpoint, items, decision = _runtime_view()
    reversed_scenario, reversed_checkpoint, reversed_items, reversed_decision = _runtime_view(reverse=True)

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=items,
        decision=decision,
    )
    reversed_result = compare_checkpoint_semantics(
        scenario=reversed_scenario,
        checkpoint=reversed_checkpoint,
        graph_items=reversed_items,
        decision=reversed_decision,
    )

    assert result.passed
    assert reversed_result == result


def test_canonical_comparison_does_not_guess_canonical_names_from_aliases() -> None:
    scenario, checkpoint, items, decision = _runtime_view(opaque_entity_names=True)

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=items,
        decision=decision,
    )

    assert not result.passed
    assert "production_retrieval_missing_expected_claim" in result.failure_buckets
    assert "production_retrieval_unexpected_selected_claim" in result.failure_buckets


def test_canonical_comparison_rejects_semantic_object_mutation() -> None:
    scenario, checkpoint, items, decision = _runtime_view(wrong_object=True)

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=items,
        decision=decision,
    )

    assert not result.passed
    assert result.failure_buckets == [
        "production_retrieval_missing_expected_claim",
        "production_retrieval_missing_expected_support",
        "production_retrieval_unexpected_selected_claim",
        "production_retrieval_unexpected_supporting_claim",
    ]


def test_expected_exclusion_may_be_classified_as_context() -> None:
    scenario, checkpoint, items, decision = _runtime_view()
    contextualized = decision.model_copy(
        update={
            "context_record_ids": decision.rejected_record_ids,
            "rejected_record_ids": [],
        }
    )

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=items,
        decision=contextualized,
    )

    assert result.passed


def test_exclusion_is_not_required_when_checkpoint_contract_disables_it() -> None:
    scenario, checkpoint, items, decision = _runtime_view()
    optional_exclusion = checkpoint.model_copy(
        update={
            "task_contract": checkpoint.task_contract.model_copy(
                update={"excluded_ids_must_be_rejected_or_contextualized": False}
            )
        }
    )
    without_exclusion = decision.model_copy(update={"rejected_record_ids": []})

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=optional_exclusion,
        graph_items=items,
        decision=without_exclusion,
    )

    assert result.passed


def test_action_selection_takes_precedence_over_duplicate_claim_projection() -> None:
    scenario = next(
        item
        for item in generate_memory_evolution_sim_scenarios(
            profile="adversarial",
            scenario_count=10,
            seed=7,
            noise_rate=0.35,
        )
        if item.family == "abandoned_then_resumed_work"
    )
    checkpoint = scenario.checkpoints[0].model_copy(update={"expected_excluded_claim_ids": []})
    claim_id = checkpoint.expected_execution_claim_ids[0]
    claim = next(item for item in scenario.claims if item.claim_id == claim_id)
    entity = next(item for item in scenario.entities if item.entity_id == claim.subject.entity_id)
    runtime_entity_id = "runtime:branch"
    runtime_claim_id = "runtime:action-state"
    items: list[RuntimeGraphItem] = [
        RuntimeEntityGraphItemRow(
            scenario_id="runtime-scenario",
            runtime_item_id=runtime_entity_id,
            canonical_id="opaque:branch",
            canonical_name=entity.canonical_name,
            entity_type=entity.entity_type,
            aliases=[alias.alias_text for alias in entity.aliases],
            lifecycle_state="active",
            evidence_event_ids=[],
        ),
        RuntimeClaimGraphItemRow(
            scenario_id="runtime-scenario",
            runtime_item_id=f"graph:{runtime_claim_id}",
            claim_id=runtime_claim_id,
            subject_entity_id=runtime_entity_id,
            predicate=claim.predicate.predicate_id,
            object=claim.object.value,
            object_value=claim.object.normalized_value or claim.object.value,
            scope=claim.scope.scope_key,
            valid_from=claim.lifecycle.valid_from.isoformat(),
            lifecycle_state="invalidated",
            evidence_event_ids=list(claim.evidence.source_event_ids),
        ),
        RuntimeActionGraphItemRow(
            scenario_id="runtime-scenario",
            runtime_item_id=f"graph:action:{runtime_claim_id}",
            action_id=f"action:{runtime_claim_id}",
            action_type=claim.predicate.predicate_id,
            status=claim.object.normalized_value or claim.object.value,
            target_entity_ids=[runtime_entity_id],
            lifecycle_state="active",
            evidence_event_ids=list(claim.evidence.source_event_ids),
        ),
    ]
    decision = ProductionRetrievalDecision(
        query=checkpoint.query_or_task,
        semantic_frame_status="matched",
        temporal_frame={},
        selected_record_ids=[runtime_claim_id],
        supporting_record_ids=[runtime_claim_id],
    )

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=items,
        decision=decision,
    )

    assert result.passed


def test_canonical_comparison_rejects_dangling_channel_record() -> None:
    scenario, checkpoint, items, decision = _runtime_view()
    dangling = decision.model_copy(update={"context_record_ids": ["runtime:missing"]})

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_items=items,
        decision=dangling,
    )

    assert "production_retrieval_unresolved_channel_record" in result.failure_buckets


def test_canonical_comparison_checks_expected_uncertainty() -> None:
    scenario, checkpoint, items, decision = _runtime_view()
    expected_uncertain = checkpoint.model_copy(
        update={"expected_uncertain_ids": [checkpoint.expected_excluded_claim_ids[0]]}
    )

    result = compare_checkpoint_semantics(
        scenario=scenario,
        checkpoint=expected_uncertain,
        graph_items=items,
        decision=decision,
    )

    assert "production_retrieval_missing_expected_uncertainty" in result.failure_buckets


def test_canonical_comparator_does_not_import_runtime_alignment() -> None:
    from memorii.core.benchmark.memory_evolution_runtime import semantic_comparison

    module = ast.parse(inspect.getsource(semantic_comparison))
    imported_modules = {
        alias.name for node in ast.walk(module) if isinstance(node, ast.Import) for alias in node.names
    } | {node.module or "" for node in ast.walk(module) if isinstance(node, ast.ImportFrom)}

    assert not any(".alignment" in module_name for module_name in imported_modules)
    assert not any(".judges" in module_name for module_name in imported_modules)
    assert not any("checkpoint_projection" in module_name for module_name in imported_modules)
    assert "_observed" not in inspect.getsource(semantic_comparison._expected_view)
    assert "_expected" not in inspect.getsource(semantic_comparison._observed_view)
