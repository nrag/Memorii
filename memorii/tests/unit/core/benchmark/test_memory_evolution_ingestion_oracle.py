from __future__ import annotations

from pathlib import Path

import pytest
from memorii.core.benchmark.memory_evolution_runtime.ingestion_oracle import (
    audit_ingestion_prefix,
)
from memorii.core.benchmark.memory_evolution_runtime.models import RuntimeGraphSnapshotRow
from memorii.core.benchmark.memory_evolution_runtime.runner import run_runtime_scenarios
from memorii.core.benchmark.memory_evolution_sim import (
    LatentGraphScenario,
    generate_memory_evolution_sim_scenarios,
)
from memorii.core.memory_evolution import (
    MemoryGraphEdge,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    RecordLifecycleState,
)
from tests.support.memory_evolution_provider_harness import MemoryEvolutionProviderHarness


@pytest.fixture(scope="module")
def ownership_graph() -> tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]]:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=1,
        seed=7,
        noise_rate=0.35,
    )[0]
    rows = run_runtime_scenarios(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=Path("memorii/memorii/prompts"),
        provider_factory=MemoryEvolutionProviderHarness,
    )
    assert rows.ingestion_prefix_audits
    assert all(row.passed for row in rows.ingestion_prefix_audits)
    return scenario, _snapshot(rows.graph_snapshots[-1]), _source_event_map(scenario)


@pytest.fixture(scope="module")
def action_graph() -> tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]]:
    scenario = generate_memory_evolution_sim_scenarios(
        profile="adversarial",
        scenario_count=10,
        seed=7,
        noise_rate=0.35,
    )[9]
    rows = run_runtime_scenarios(
        scenarios=[scenario],
        mode="llm",
        dry_run=True,
        allow_live=False,
        prompt_root=Path("memorii/memorii/prompts"),
        provider_factory=MemoryEvolutionProviderHarness,
    )
    assert all(row.passed for row in rows.ingestion_prefix_audits)
    return scenario, _snapshot(rows.graph_snapshots[-1]), _source_event_map(scenario)


def test_oracle_detects_wrong_owner(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    claim = _current_owner_claim(snapshot)
    owner_edge = _edge(snapshot, claim.node_id, MemoryGraphEdgeType.HAS_OBJECT)
    wrong_person = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.ENTITY
        and node.properties.get("entity_type") == "person"
        and node.node_id != owner_edge.target_node_id
    )
    mutated = snapshot.model_copy(
        update={
            "edges": [
                edge.model_copy(update={"target_node_id": wrong_person.node_id})
                if edge.edge_id == owner_edge.edge_id
                else edge
                for edge in snapshot.edges
            ]
        }
    )

    assert "ingestion_claim_object_mismatch" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_swapped_claim_endpoints(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    claim = _current_owner_claim(snapshot)
    subject_edge = _edge(snapshot, claim.node_id, MemoryGraphEdgeType.HAS_SUBJECT)
    object_edge = _edge(snapshot, claim.node_id, MemoryGraphEdgeType.HAS_OBJECT)
    mutated = snapshot.model_copy(
        update={
            "edges": [
                edge.model_copy(update={"target_node_id": object_edge.target_node_id})
                if edge.edge_id == subject_edge.edge_id
                else edge.model_copy(update={"target_node_id": subject_edge.target_node_id})
                if edge.edge_id == object_edge.edge_id
                else edge
                for edge in snapshot.edges
            ]
        }
    )

    issue_codes = _issue_codes(scenario, mutated, source_map)
    assert "ingestion_claim_predicate_mismatch" in issue_codes
    assert "ingestion_unexpected_observed_claim" in issue_codes


def test_oracle_detects_missing_claim_object_endpoint(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    claim = _current_owner_claim(snapshot)
    object_edge = _edge(snapshot, claim.node_id, MemoryGraphEdgeType.HAS_OBJECT)
    mutated = snapshot.model_copy(
        update={"edges": [edge for edge in snapshot.edges if edge.edge_id != object_edge.edge_id]}
    )

    assert "ingestion_claim_object_mismatch" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_wrong_predicate(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    claim = _current_owner_claim(snapshot)
    mutated = snapshot.model_copy(
        update={
            "nodes": [
                node.model_copy(
                    update={
                        "properties": {
                            **node.properties,
                            "predicate_id": "status",
                        }
                    }
                )
                if node.node_id == claim.node_id
                else node
                for node in snapshot.nodes
            ]
        }
    )

    assert "ingestion_claim_predicate_mismatch" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_wrong_entity_type(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    project = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.ENTITY and node.properties.get("entity_type") == "project"
    )
    mutated = snapshot.model_copy(
        update={
            "nodes": [
                node.model_copy(
                    update={
                        "properties": {
                            **node.properties,
                            "entity_type": "service",
                        }
                    }
                )
                if node.node_id == project.node_id
                else node
                for node in snapshot.nodes
            ]
        }
    )

    assert "ingestion_entity_type_mismatch" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_entity_merge(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    people = [
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.ENTITY
        and node.properties.get("entity_type") == "person"
        and node.properties.get("scope_key") == "global"
    ]
    primary, duplicate = people[:2]
    merged_observed_names = "|".join(
        sorted(
            {
                primary.label,
                duplicate.label,
                primary.properties.get("normalized_name", ""),
                duplicate.properties.get("normalized_name", ""),
                *primary.properties.get("observed_names", "").split("|"),
                *duplicate.properties.get("observed_names", "").split("|"),
            }
        )
    )
    mutated_primary = primary.model_copy(
        update={
            "properties": {
                **primary.properties,
                "observed_names": merged_observed_names,
            }
        }
    )
    mutated = snapshot.model_copy(
        update={
            "nodes": [
                mutated_primary if node.node_id == primary.node_id else node
                for node in snapshot.nodes
                if node.node_id != duplicate.node_id
            ],
            "edges": [
                edge.model_copy(
                    update={
                        "source_node_id": (
                            primary.node_id if edge.source_node_id == duplicate.node_id else edge.source_node_id
                        ),
                        "target_node_id": (
                            primary.node_id if edge.target_node_id == duplicate.node_id else edge.target_node_id
                        ),
                    }
                )
                for edge in snapshot.edges
            ],
        }
    )

    assert "ingestion_unexpected_entity_merge" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_entity_split(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    project = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.ENTITY and node.properties.get("entity_type") == "project"
    )
    duplicate = project.model_copy(
        update={
            "node_id": f"{project.node_id}:duplicate",
            "canonical_id": f"{project.canonical_id}:duplicate",
            "payload_ref": f"{project.payload_ref}:duplicate",
        }
    )
    mutated = snapshot.model_copy(update={"nodes": [*snapshot.nodes, duplicate]})

    assert "ingestion_unexpected_entity_split" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_wrong_action_state(
    action_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = action_graph
    action = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.ACTION and node.properties.get("execution_status") == "in_progress"
    )
    mutated = snapshot.model_copy(
        update={
            "nodes": [
                node.model_copy(
                    update={
                        "properties": {
                            **node.properties,
                            "status": "failed",
                            "execution_status": "failed",
                        }
                    }
                )
                if node.node_id == action.node_id
                else node
                for node in snapshot.nodes
            ]
        }
    )

    assert "ingestion_action_status_mismatch" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_missing_provenance(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    claim = _current_owner_claim(snapshot)
    mutated = snapshot.model_copy(
        update={
            "edges": [
                edge.model_copy(
                    update={
                        "source_record_ids": [],
                        "evidence_span_ids": [],
                    }
                )
                if edge.source_node_id == claim.node_id and edge.edge_type == MemoryGraphEdgeType.OBSERVED_IN
                else edge
                for edge in snapshot.edges
            ]
        }
    )

    assert "ingestion_claim_provenance_mismatch" in _issue_codes(scenario, mutated, source_map)


def test_oracle_allows_extra_corroborating_claim_provenance(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    claim = _current_owner_claim(snapshot)
    observed_edge = _edge(snapshot, claim.node_id, MemoryGraphEdgeType.OBSERVED_IN)
    extra_source_id = next(source_id for source_id in source_map if source_id not in observed_edge.source_record_ids)
    mutated = snapshot.model_copy(
        update={
            "edges": [
                edge.model_copy(
                    update={
                        "source_record_ids": [
                            *edge.source_record_ids,
                            extra_source_id,
                        ]
                    }
                )
                if edge.edge_id == observed_edge.edge_id
                else edge
                for edge in snapshot.edges
            ]
        }
    )

    assert "ingestion_claim_provenance_mismatch" not in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_missing_relation(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    mutated = snapshot.model_copy(
        update={"edges": [edge for edge in snapshot.edges if edge.edge_type != MemoryGraphEdgeType.ALIAS_OF]}
    )

    assert "ingestion_missing_expected_relation" in _issue_codes(scenario, mutated, source_map)


def test_oracle_detects_unexpected_entity(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    template = next(node for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.ENTITY)
    extra = template.model_copy(
        update={
            "node_id": "entity:unexpected",
            "canonical_id": "entity:unexpected",
            "label": "Unexpected",
            "properties": {
                **template.properties,
                "normalized_name": "unexpected",
                "aliases": "unexpected",
            },
        }
    )

    assert "ingestion_unexpected_observed_entity" in _issue_codes(
        scenario,
        snapshot.model_copy(update={"nodes": [*snapshot.nodes, extra]}),
        source_map,
    )


def test_oracle_detects_unexpected_claim(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    template = _current_owner_claim(snapshot)
    extra = template.model_copy(
        update={
            "node_id": "claim:unexpected",
            "canonical_id": "claim:unexpected",
            "label": "unexpected semantic fact",
            "properties": {
                **template.properties,
                "predicate_id": "semantic_fact",
            },
        }
    )

    assert "ingestion_unexpected_observed_claim" in _issue_codes(
        scenario,
        snapshot.model_copy(update={"nodes": [*snapshot.nodes, extra]}),
        source_map,
    )


def test_oracle_detects_fully_connected_unexpected_historical_claim(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    template = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.CLAIM
        and node.lifecycle_state == RecordLifecycleState.SUPERSEDED
        and node.properties.get("predicate_id") == "owner"
    )
    current = _current_owner_claim(snapshot)
    current_owner = _edge(
        snapshot,
        current.node_id,
        MemoryGraphEdgeType.HAS_OBJECT,
    ).target_node_id
    extra_id = "claim:unexpected-historical"
    extra = template.model_copy(
        update={
            "node_id": extra_id,
            "canonical_id": extra_id,
            "label": "unexpected historical owner",
            "properties": {
                **template.properties,
                "claim_id": extra_id,
                "object_value": "unexpected historical owner",
            },
        }
    )
    extra_edges = [
        edge.model_copy(
            update={
                "edge_id": f"{edge.edge_id}:unexpected-historical",
                "source_node_id": extra_id,
                "target_node_id": (
                    current_owner if edge.edge_type == MemoryGraphEdgeType.HAS_OBJECT else edge.target_node_id
                ),
            }
        )
        for edge in snapshot.edges
        if edge.source_node_id == template.node_id
    ]

    assert "ingestion_unexpected_observed_claim" in _issue_codes(
        scenario,
        snapshot.model_copy(
            update={
                "nodes": [*snapshot.nodes, extra],
                "edges": [*snapshot.edges, *extra_edges],
            }
        ),
        source_map,
    )


def test_oracle_detects_unexpected_action(
    action_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = action_graph
    template = next(node for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.ACTION)
    extra = template.model_copy(
        update={
            "node_id": "action:unexpected",
            "canonical_id": "action:unexpected",
        }
    )

    assert "ingestion_unexpected_observed_action" in _issue_codes(
        scenario,
        snapshot.model_copy(update={"nodes": [*snapshot.nodes, extra]}),
        source_map,
    )


def test_oracle_detects_unexpected_semantic_relation(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
) -> None:
    scenario, snapshot, source_map = ownership_graph
    entities = [node for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.ENTITY]
    template = snapshot.edges[0]
    extra = template.model_copy(
        update={
            "edge_id": "relation:unexpected",
            "edge_type": MemoryGraphEdgeType.DEPENDS_ON,
            "source_node_id": entities[0].node_id,
            "target_node_id": entities[1].node_id,
        }
    )

    assert "ingestion_unexpected_observed_relation" in _issue_codes(
        scenario,
        snapshot.model_copy(update={"edges": [*snapshot.edges, extra]}),
        source_map,
    )


@pytest.mark.parametrize(
    "edge_type",
    [
        MemoryGraphEdgeType.CONFLICTS_WITH,
        MemoryGraphEdgeType.SUPERSEDES,
    ],
)
def test_oracle_detects_unexpected_claim_lineage_relation(
    ownership_graph: tuple[LatentGraphScenario, MemoryGraphSnapshot, dict[str, str]],
    edge_type: MemoryGraphEdgeType,
) -> None:
    scenario, snapshot, source_map = ownership_graph
    owner_claims = [
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.CLAIM and node.properties.get("predicate_id") == "owner"
    ]
    current = _current_owner_claim(snapshot)
    target = next(
        node
        for node in owner_claims
        if node.node_id != current.node_id
        and not any(
            edge.edge_type == edge_type
            and edge.source_node_id == current.node_id
            and edge.target_node_id == node.node_id
            for edge in snapshot.edges
        )
    )
    template = snapshot.edges[0]
    extra = template.model_copy(
        update={
            "edge_id": f"relation:unexpected:{edge_type.value}",
            "edge_type": edge_type,
            "source_node_id": current.node_id,
            "target_node_id": target.node_id,
        }
    )

    assert "ingestion_unexpected_observed_relation" in _issue_codes(
        scenario,
        snapshot.model_copy(update={"edges": [*snapshot.edges, extra]}),
        source_map,
    )


def _issue_codes(
    scenario: LatentGraphScenario,
    snapshot: MemoryGraphSnapshot,
    source_map: dict[str, str],
) -> set[str]:
    observations = sorted(
        scenario.observations,
        key=lambda observation: (observation.timestamp, observation.event_id),
    )
    return {
        issue.code
        for issue in audit_ingestion_prefix(
            scenario=scenario,
            observations=observations,
            snapshot=snapshot,
            source_id_to_event_id=source_map,
        ).issues
    }


def _source_event_map(scenario: LatentGraphScenario) -> dict[str, str]:
    return {
        f"tx:benchmark:runtime:{observation.event_id}": observation.event_id for observation in scenario.observations
    }


def _current_owner_claim(snapshot: MemoryGraphSnapshot) -> MemoryGraphNode:
    return next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.CLAIM
        and node.lifecycle_state == RecordLifecycleState.ACTIVE
        and node.properties.get("predicate_id") == "owner"
        and node.properties.get("object_value") not in {"Alice", "Priya", "Marta", "Eli"}
    )


def _edge(
    snapshot: MemoryGraphSnapshot,
    source_node_id: str,
    edge_type: MemoryGraphEdgeType,
) -> MemoryGraphEdge:
    return next(
        edge for edge in snapshot.edges if edge.source_node_id == source_node_id and edge.edge_type == edge_type
    )


def _snapshot(row: RuntimeGraphSnapshotRow) -> MemoryGraphSnapshot:
    return MemoryGraphSnapshot(
        snapshot_id=row.snapshot_id,
        nodes=list(row.nodes),
        edges=list(row.edges),
        validation_errors=list(row.validation_errors),
    )
