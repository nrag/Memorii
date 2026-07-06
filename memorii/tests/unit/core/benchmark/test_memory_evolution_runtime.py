from memorii.core.benchmark.memory_evolution_runtime import (
    RuntimeSuiteRows,
    align_runtime_graph_to_oracle,
    runtime_graph_completeness_metrics,
)
from memorii.core.benchmark.memory_evolution_sim import generate_memory_evolution_sim_scenarios


def _runtime_entity(*, scenario_id: str, runtime_id: str, canonical_id: str, name: str, entity_type: str, aliases: list[str], events: list[str]) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "runtime_item_id": runtime_id,
        "item_type": "entity",
        "canonical_name": name,
        "canonical_id": canonical_id,
        "entity_type": entity_type,
        "aliases": aliases,
        "lifecycle_state": "active",
        "confidence": 0.9,
        "evidence_event_ids": events,
    }


def _runtime_claim(*, scenario_id: str, runtime_id: str, subject_id: str, subject: str, predicate: str, obj: str, event: str) -> dict[str, object]:
    return {
        "scenario_id": scenario_id,
        "runtime_item_id": runtime_id,
        "item_type": "claim",
        "claim_id": runtime_id,
        "subject": subject,
        "subject_entity_id": subject_id,
        "predicate": predicate,
        "object": obj,
        "object_value": obj,
        "scope": "global",
        "valid_from": "",
        "valid_to": "",
        "lifecycle_state": "active",
        "confidence": 0.9,
        "evidence_event_ids": [event],
    }


def _alignment_for(alignments, oracle_id: str):
    return next(item for item in alignments if item.oracle_item_id == oracle_id and item.item_type == "claim")


def test_runtime_claim_alignment_uses_entity_alias_for_service_owner() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=["event_00_003"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj="Iris",
            event="event_00_003",
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    service_owner = _alignment_for(alignments, "claim_00_service_owner")
    ambiguous_project_owner = _alignment_for(alignments, "claim_00_ambiguous_service_owner_atlas")
    assert service_owner.verdict.value == "aligned"
    assert "subject_entity" in service_owner.matched_on
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_claim_alignment_uses_atlas_alias_for_historical_project_owner() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=2, seed=7)[1]
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas",
            canonical_id="ent:atlas",
            name="atlas",
            entity_type="unknown",
            aliases=["Atlas"],
            events=["event_01_002"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:previous-owner",
            subject_id="ent:atlas",
            subject="atlas",
            predicate="owner",
            obj="Alice",
            event="event_01_002",
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    previous_owner = _alignment_for(alignments, "claim_01_previous_owner_old")
    assert previous_owner.verdict.value == "aligned"
    assert "subject_entity" in previous_owner.matched_on


def test_runtime_claim_alignment_does_not_merge_service_into_project() -> None:
    scenario = generate_memory_evolution_sim_scenarios(profile="smoke", scenario_count=1, seed=7)[0]
    graph_items = [
        _runtime_entity(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:entity:atlas-service",
            canonical_id="ent:atlas-service",
            name="atlas service",
            entity_type="service",
            aliases=["Atlas service"],
            events=["event_00_003"],
        ),
        _runtime_claim(
            scenario_id=scenario.scenario_id,
            runtime_id="rt:claim:service-owner",
            subject_id="ent:atlas-service",
            subject="atlas service",
            predicate="owner",
            obj="Iris",
            event="event_00_003",
        ),
    ]

    alignments = align_runtime_graph_to_oracle(scenario=scenario, graph_items=graph_items)

    ambiguous_project_owner = _alignment_for(alignments, "claim_00_ambiguous_service_owner_atlas")
    assert ambiguous_project_owner.verdict.value != "aligned"


def test_runtime_graph_completeness_metrics_report_claim_provenance_and_edge_counts() -> None:
    rows = RuntimeSuiteRows(
        scenario_rows=[],
        checkpoint_rows=[
            {
                "runtime_relation_support": [
                    {"relation_id": "rel_claim_derived", "support_mode": "claim_derived"},
                    {"relation_id": "rel_item", "support_mode": "runtime_relation_item"},
                ]
            }
        ],
        judge_rows=[],
        llm_rows=[],
        graph_items=[
            {"item_type": "claim"},
            {"item_type": "entity"},
            {"item_type": "relation"},
            {"item_type": "action"},
        ],
        graph_snapshots=[
            {
                "validation_errors": [],
                "nodes": [
                    {"node_id": "source:1", "node_type": "source_observation"},
                    {"node_id": "claim:1", "node_type": "claim", "lifecycle_state": "active"},
                    {"node_id": "entity:1", "node_type": "entity"},
                    {"node_id": "literal:1", "node_type": "literal"},
                    {"node_id": "scope:global", "node_type": "scope"},
                ],
                "edges": [
                    {"edge_type": "has_subject", "source_node_id": "claim:1", "target_node_id": "entity:1"},
                    {"edge_type": "has_literal_object", "source_node_id": "claim:1", "target_node_id": "literal:1"},
                    {"edge_type": "has_scope", "source_node_id": "claim:1", "target_node_id": "scope:global"},
                    {"edge_type": "observed_in", "source_node_id": "claim:1", "target_node_id": "source:1"},
                ],
            }
        ],
    )

    metrics = runtime_graph_completeness_metrics(rows)

    assert metrics["source_observation_count"] == 1
    assert metrics["entity_count"] == 1
    assert metrics["claim_count"] == 1
    assert metrics["relation_item_count"] == 1
    assert metrics["action_item_count"] == 1
    assert metrics["evidence_edge_count"] == 1
    assert metrics["active_claim_with_subject_rate"] == 1.0
    assert metrics["active_claim_with_object_or_literal_rate"] == 1.0
    assert metrics["active_claim_with_scope_rate"] == 1.0
    assert metrics["active_claim_with_observed_in_rate"] == 1.0
    assert metrics["runtime_relation_support_modes"] == {
        "claim_derived": 1,
        "runtime_relation_item": 1,
    }
