from __future__ import annotations

from memorii.core.benchmark.memory_evolution_runtime import (
    align_runtime_graph_to_oracle,
    expected_action_alignment_rows,
    project_runtime_checkpoint,
)
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_evaluation import runtime_failure_buckets
from memorii.core.benchmark.memory_evolution_runtime.checkpoint_projection import (
    _oracle_ids_for_runtime_claim_ids,
    runtime_answer_for_checkpoint,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeRelationGraphItemRow
from memorii.core.memory_evolution.models import MemoryGraphSnapshot
from memorii.core.memory_evolution.retrieval_contracts import ProductionRetrievalDecision, SemanticFrameStatus
from memorii.core.memory_evolution.temporal_contracts import QueryTemporalFrame
from tests.unit.core.benchmark.memory_evolution_runtime_test_helpers import (
    action_claim_by_state,
    alignment_for,
    claim_event_id,
    long_horizon_execution_scenario,
    runtime_action,
    runtime_claim,
    runtime_entity,
)
from tests.unit.core.benchmark.memory_evolution_test_helpers import (
    checkpoint_by_type,
    claim_by_role,
    generate_scenario_by_family,
)


def _action_alignment_rows(
    *,
    scenario,
    checkpoint,
    runtime_action_item,
    oracle_target_entity_id: str,
):
    oracle_entity = next(entity for entity in scenario.entities if entity.entity_id == oracle_target_entity_id)
    runtime_target_id = "runtime:opaque-action-target"
    entity_item = runtime_entity(
        scenario_id=scenario.scenario_id,
        runtime_id="runtime:opaque-action-target-node",
        canonical_id=runtime_target_id,
        name=oracle_entity.canonical_name,
        entity_type=oracle_entity.entity_type,
        aliases=[alias.alias_text for alias in oracle_entity.aliases],
        events=[],
    )
    action_item = runtime_action_item.model_copy(update={"target_entity_ids": [runtime_target_id]})
    graph_items = [entity_item, action_item]
    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)
    return expected_action_alignment_rows(
        scenario=scenario,
        expected_action_ids=checkpoint.expected_action_ids,
        graph_items=graph_items,
        runtime_claim_by_oracle={},
        entity_alignments=alignments,
    )


def _runtime_relation_alignment(*, scenario, relation, source_item, target_item, **updates):
    runtime_relation = RuntimeRelationGraphItemRow(
        scenario_id=scenario.scenario_id,
        runtime_item_id="runtime:opaque-relation",
        relation_type=relation.relation_type,
        source=source_item.runtime_item_id,
        target=target_item.runtime_item_id,
        directionality=relation.directionality,
        lifecycle_state="active",
    ).model_copy(update=updates)
    alignments = align_runtime_graph_to_oracle(
        scenario=scenario,
        graph_items=[source_item, target_item, runtime_relation],
    )
    return next(
        row
        for row in alignments
        if row.item_type == "relation" and row.runtime_item_id == runtime_relation.runtime_item_id
    )


def test_runtime_relation_alignment_composes_independent_claim_alignment() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    relation = next(item for item in scenario.relations if item.relation_type == "contradicts")
    source_claim = next(item for item in scenario.claims if item.claim_id == relation.source.endpoint_id)
    target_claim = next(item for item in scenario.claims if item.claim_id == relation.target.endpoint_id)
    source_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id="runtime:opaque-source",
        subject_id="runtime:source-subject",
        subject=source_claim.subject.canonical_name,
        predicate=source_claim.predicate.predicate_id,
        obj=source_claim.object.value,
        event=claim_event_id(source_claim),
    ).model_copy(update={"claim_id": source_claim.claim_id})
    target_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id="runtime:opaque-target",
        subject_id="runtime:target-subject",
        subject=target_claim.subject.canonical_name,
        predicate=target_claim.predicate.predicate_id,
        obj=target_claim.object.value,
        event=claim_event_id(target_claim),
    ).model_copy(update={"claim_id": target_claim.claim_id})

    aligned = _runtime_relation_alignment(
        scenario=scenario,
        relation=relation,
        source_item=source_item,
        target_item=target_item,
    )
    reversed_edge = _runtime_relation_alignment(
        scenario=scenario,
        relation=relation,
        source_item=source_item,
        target_item=target_item,
        source=target_item.runtime_item_id,
        target=source_item.runtime_item_id,
    )
    wrong_type = _runtime_relation_alignment(
        scenario=scenario,
        relation=relation,
        source_item=source_item,
        target_item=target_item,
        relation_type="supersedes",
    )
    wrong_direction = _runtime_relation_alignment(
        scenario=scenario,
        relation=relation,
        source_item=source_item,
        target_item=target_item,
        directionality="undirected",
    )

    assert aligned.verdict.value == "aligned"
    assert aligned.matched_on == [
        "source_alignment",
        "target_alignment",
        "relation_type",
        "directionality",
    ]
    assert reversed_edge.verdict.value != "aligned"
    assert wrong_type.verdict.value != "aligned"
    assert wrong_direction.verdict.value != "aligned"


def test_runtime_claim_alignment_uses_entity_alias_for_service_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    service_owner_claim = next(
        claim
        for claim in scenario.claims
        if "entity_disambiguation" in claim.evaluation_roles and claim.predicate.predicate_id == "owner"
    )
    ambiguous_project_claim = claim_by_role(scenario, "conflict_detection")
    evidence_event_id = claim_event_id(service_owner_claim)
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=[evidence_event_id],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj=service_owner_claim.object.value,
            event=evidence_event_id,
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    service_owner = alignment_for(alignments, service_owner_claim.claim_id)
    ambiguous_project_owner = alignment_for(alignments, ambiguous_project_claim.claim_id)
    assert service_owner.verdict.value == "aligned"
    assert "subject_entity" in service_owner.matched_on
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_partial_rejected_claim_alignment_remains_visible_and_fails_closed() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="same_entity_vocabulary_different_role",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "entity_disambiguation")
    excluded_claim = next(
        claim for claim in scenario.claims if claim.claim_id in checkpoint.expected_excluded_claim_ids
    )
    evidence_event_id = claim_event_id(excluded_claim)
    runtime_claim_id = excluded_claim.claim_id
    partial_claim = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id="runtime:partial-rejected-claim",
        subject_id="runtime:partial-rejected-subject",
        subject=excluded_claim.subject.canonical_name,
        predicate=excluded_claim.predicate.predicate_id,
        obj=excluded_claim.object.value,
        event=evidence_event_id,
    ).model_copy(update={"claim_id": runtime_claim_id, "evidence_event_ids": []})
    graph_items = [partial_claim]
    decision = ProductionRetrievalDecision(
        query=checkpoint.query_or_task,
        semantic_frame_status=SemanticFrameStatus.MATCHED,
        temporal_frame=QueryTemporalFrame(),
        rejected_record_ids=[runtime_claim_id],
    )
    snapshot = MemoryGraphSnapshot(snapshot_id="partial-rejection")

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=snapshot,
        graph_items=graph_items,
        source_id_to_event_id={},
        retrieval_decision=decision,
    )

    partial_rows = [
        row
        for row in projection.channel_alignment_rows
        if row.channel == "rejected"
        and row.oracle_id == excluded_claim.claim_id
        and row.verdict == "partial"
    ]
    assert partial_rows
    assert excluded_claim.claim_id not in projection.output.rejected_claim_ids
    assert "production_retrieval_missing_expected_rejection" in runtime_failure_buckets(
        checkpoint=checkpoint,
        output=projection.output,
        projection=projection,
        graph_snapshot=snapshot,
    )


def test_nonaligned_production_selected_claim_remains_visible_and_fails_closed() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    checkpoint = checkpoint_by_type(scenario, "current_truth")
    runtime_claim_id = "runtime:unexpected-selected-claim"
    unexpected_claim = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=runtime_claim_id,
        subject_id="runtime:unrelated-subject",
        subject="Unrelated Subject",
        predicate="semantic_fact",
        obj="Unrelated Value",
        event="runtime:unrelated-event",
    )
    decision = ProductionRetrievalDecision(
        query=checkpoint.query_or_task,
        semantic_frame_status=SemanticFrameStatus.MATCHED,
        temporal_frame=QueryTemporalFrame(),
        selected_record_ids=[runtime_claim_id],
        supporting_record_ids=[runtime_claim_id],
    )
    snapshot = MemoryGraphSnapshot(snapshot_id="unexpected-selection")

    projection = project_runtime_checkpoint(
        scenario=scenario,
        checkpoint=checkpoint,
        graph_snapshot=snapshot,
        graph_items=[unexpected_claim],
        source_id_to_event_id={},
        retrieval_decision=decision,
    )

    assert projection.production_channels.selected_claim_ids == (runtime_claim_id,)
    assert any(
        row.channel == "selected"
        and row.runtime_id == runtime_claim_id
        and row.verdict != "aligned"
        for row in projection.channel_alignment_rows
    )
    assert "production_retrieval_unexpected_selected_claim" in runtime_failure_buckets(
        checkpoint=checkpoint,
        output=projection.output,
        projection=projection,
        graph_snapshot=snapshot,
    )


def test_runtime_claim_alignment_uses_atlas_alias_for_historical_project_owner() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    previous_owner_claim = claim_by_role(scenario, "historical_truth")
    evidence_event_id = claim_event_id(previous_owner_claim)
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas",
            canonical_id="ent:atlas",
            name="atlas",
            entity_type="unknown",
            aliases=["Atlas"],
            events=[evidence_event_id],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:previous-owner",
            subject_id="ent:atlas",
            subject="atlas",
            predicate="owner",
            obj="Alice",
            event=evidence_event_id,
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    previous_owner = alignment_for(alignments, previous_owner_claim.claim_id)
    assert previous_owner.verdict.value == "aligned"
    assert "subject_entity" in previous_owner.matched_on


def test_runtime_action_semantically_aligns_to_oracle_action_with_native_id() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")

    rows = _action_alignment_rows(
        scenario=scenario,
        checkpoint=checkpoint,
        runtime_action_item=runtime_action(
            target="ignored", status="in_progress", events=[claim_event_id(progress)]
        ),
        oracle_target_entity_id=progress.subject.entity_id,
    )

    assert rows[0].verdict == "aligned"
    assert rows[0].support_mode == "runtime_action_semantic"
    assert rows[0].matched_on == ["target_entity", "status", "evidence_event", "lifecycle"]


def test_runtime_action_alignment_classifies_target_status_and_evidence_failures() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")
    progress_event = claim_event_id(progress)

    wrong_target_claim = action_claim_by_state(
        scenario, "blocked", subject_name="Atlas Cleanup Branch A"
    )
    wrong_target = _action_alignment_rows(
        scenario=scenario,
        checkpoint=checkpoint,
        runtime_action_item=runtime_action(target="ignored", status="in_progress", events=[progress_event]),
        oracle_target_entity_id=wrong_target_claim.subject.entity_id,
    )[0]
    wrong_status = _action_alignment_rows(
        scenario=scenario,
        checkpoint=checkpoint,
        runtime_action_item=runtime_action(target="ignored", status="started", events=[progress_event]),
        oracle_target_entity_id=progress.subject.entity_id,
    )[0]
    missing_evidence = _action_alignment_rows(
        scenario=scenario,
        checkpoint=checkpoint,
        runtime_action_item=runtime_action(target="ignored", status="in_progress", events=[]),
        oracle_target_entity_id=progress.subject.entity_id,
    )[0]

    assert wrong_target.verdict == "partial"
    assert wrong_target.failure_reason == "runtime_action_target_mismatch"
    assert wrong_status.failure_reason == "runtime_action_status_mismatch"
    assert missing_evidence.failure_reason == "runtime_action_evidence_missing"


def test_runtime_action_alignment_derives_progress_status_from_action_type() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")

    rows = _action_alignment_rows(
        scenario=scenario,
        checkpoint=checkpoint,
        runtime_action_item=runtime_action(
            target="ignored",
            status="started",
            action_type="in_progress",
            events=[claim_event_id(progress)],
        ),
        oracle_target_entity_id=progress.subject.entity_id,
    )

    assert rows[0].verdict == "aligned"
    assert rows[0].status == "in_progress"
    assert rows[0].status_derived_from == "action_type"


def test_runtime_action_alignment_prefers_explicit_progress_over_resume_verb() -> None:
    scenario, checkpoint = long_horizon_execution_scenario()
    progress = action_claim_by_state(scenario, "in_progress", subject_name="Atlas Cleanup Branch B")

    rows = _action_alignment_rows(
        scenario=scenario,
        checkpoint=checkpoint,
        runtime_action_item=runtime_action(
            target="ignored",
            status="in_progress",
            action_type="resume",
            events=[claim_event_id(progress)],
        ),
        oracle_target_entity_id=progress.subject.entity_id,
    )

    assert rows[0].verdict == "aligned"
    assert rows[0].status == "in_progress"
    assert rows[0].status_derived_from == "status"


def test_runtime_claim_alignment_requires_provenance_even_when_claim_id_matches() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    previous_owner_claim = claim_by_role(scenario, "historical_truth")
    graph_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=previous_owner_claim.claim_id,
        subject_id="ent:atlas",
        subject="atlas",
        predicate="owner",
        obj="Alice",
        event=claim_event_id(previous_owner_claim),
    )
    graph_item = graph_item.model_copy(update={"evidence_event_ids": []})

    alignment = alignment_for(
        align_runtime_graph_to_oracle(scenario=scenario, graph_items=[graph_item]),
        previous_owner_claim.claim_id,
    )

    assert alignment.verdict.value == "partial"
    assert alignment.rationale == "claim id matches but provenance is missing"


def test_runtime_alignment_enforces_one_to_one_oracle_claim_mapping() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="current_vs_historical_truth",
        seed=7,
    )
    previous_owner_claim = claim_by_role(scenario, "historical_truth")
    first = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=previous_owner_claim.claim_id,
        subject_id="ent:atlas",
        subject="atlas",
        predicate="owner",
        obj="Alice",
        event=claim_event_id(previous_owner_claim),
    )
    duplicate = first.model_copy(update={"runtime_item_id": "rt:duplicate-previous-owner"})
    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=[first, duplicate])
    claim_rows = [
        row
        for row in alignments
        if row.item_type == "claim"
        and row.runtime_item_id in {previous_owner_claim.claim_id, "rt:duplicate-previous-owner"}
    ]

    assert sum(row.verdict.value == "aligned" for row in claim_rows) == 1
    assert sum(row.verdict.value == "unmatched_runtime" for row in claim_rows) == 1


def test_runtime_claim_alignment_does_not_merge_service_into_project() -> None:
    scenario = generate_scenario_by_family(
        profile="smoke",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    service_owner_claim = next(
        claim
        for claim in scenario.claims
        if "entity_disambiguation" in claim.evaluation_roles and claim.predicate.predicate_id == "owner"
    )
    ambiguous_project_claim = claim_by_role(scenario, "conflict_detection")
    evidence_event_id = claim_event_id(service_owner_claim)
    graph_items = [
        runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=[evidence_event_id],
        ),
        runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj="Iris",
            event=evidence_event_id,
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    ambiguous_project_owner = alignment_for(alignments, ambiguous_project_claim.claim_id)
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_answer_projection_uses_checkpoint_policy_not_english_query_text() -> None:
    scenario = generate_scenario_by_family(profile="adversarial", family="entity_split", seed=7)
    checkpoint = next(item for item in scenario.checkpoints if item.answer_projection_policy == "claim_subject")
    runtime_claim_id = "rt:claim:service-owner"
    claim = next(item for item in scenario.claims if item.claim_id == checkpoint.expected_claim_ids[0])
    runtime_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=runtime_claim_id,
        subject_id=claim.subject.entity_id,
        subject="atlas platform service",
        predicate=claim.predicate.predicate_id,
        obj="Iris",
        event=claim_event_id(claim),
    )
    answer = runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=list(checkpoint.expected_claim_ids),
        runtime_claim_by_oracle={checkpoint.expected_claim_ids[0]: runtime_claim_id},
        item_by_id={runtime_claim_id: runtime_item},
    )

    assert checkpoint.answer_projection_policy == "claim_subject"
    assert answer == "Atlas Platform Service"


def test_runtime_answer_projection_prefers_canonical_entity_over_stored_literal() -> None:
    scenario = generate_scenario_by_family(profile="adversarial", family="entity_split", seed=7)
    checkpoint = next(
        item
        for item in scenario.checkpoints
        if item.answer_projection_policy not in {"none", "next_action", "graph_channels_only", "claim_subject"}
        and item.expected_claim_ids
    )
    claim = next(item for item in scenario.claims if item.claim_id == checkpoint.expected_claim_ids[0])
    runtime_claim_id = "graph:node:claim:canonical-object"
    runtime_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id=runtime_claim_id,
        subject_id=claim.subject.entity_id,
        subject=claim.subject.entity_id,
        predicate=claim.predicate.predicate_id,
        obj="canonical entity",
        event=claim_event_id(claim),
    ).model_copy(
        update={
            "object_entity_id": "entity:canonical",
            "object": "canonical entity",
            "object_value": "misleading stale literal",
        }
    )

    answer = runtime_answer_for_checkpoint(
        checkpoint=checkpoint,
        selected_claim_ids=[claim.claim_id],
        runtime_claim_by_oracle={claim.claim_id: runtime_claim_id},
        item_by_id={runtime_claim_id: runtime_item},
    )

    assert answer == "Canonical Entity"


def test_runtime_context_claim_ids_cross_persisted_graph_and_oracle_namespaces() -> None:
    scenario = generate_scenario_by_family(
        profile="adversarial",
        family="entity_definition_before_role_claims",
        seed=7,
    )
    claim = next(item for item in scenario.claims if item.observability.value != "hidden")
    runtime_item = runtime_claim(
        scenario_id=scenario.scenario_id,
        runtime_id="graph:node:claim:runtime-owner",
        subject_id=claim.subject.entity_id,
        subject=claim.subject.canonical_name,
        predicate=claim.predicate.predicate_id,
        obj=claim.object.value,
        event=claim_event_id(claim),
    ).model_copy(update={"claim_id": "persisted:claim:runtime-owner"})
    alignments = align_runtime_graph_to_oracle(
        scenario=scenario,
        graph_items=[runtime_item],
    )

    oracle_ids = _oracle_ids_for_runtime_claim_ids(
        claim_ids=["persisted:claim:runtime-owner"],
        graph_items=[runtime_item],
        alignments=alignments,
    )

    assert oracle_ids == [claim.claim_id]
    assert claim.claim_id not in {"persisted:claim:runtime-owner", runtime_item.runtime_item_id}
