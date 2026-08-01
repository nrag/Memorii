from datetime import UTC, datetime

from memorii.core.memory_evolution import MemoryEvolutionService
from memorii.core.memory_evolution.graph_ids import (
    claim_node_id,
    edge_id,
    entity_node_id,
    source_node_id,
)
from memorii.core.memory_evolution.graph_persistence import MemoryGraphValidator
from memorii.core.memory_evolution.models import (
    MemoryGraphEdge,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(
    memory_id: str,
    text: str,
    *,
    source_kind: str = "user",
    timestamp: datetime | None = None,
    task_id: str | None = "task:evolution",
) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind=source_kind,
        timestamp=timestamp or datetime(2026, 1, 1, tzinfo=UTC),
        task_id=task_id,
        is_raw_event=True,
    )


def test_simple_fact_writes_runtime_graph_nodes_and_edges() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    record = _record("tx:mar", "Atlas owner is Bob.", timestamp=datetime(2026, 3, 1, tzinfo=UTC))

    result = service.evolve_records([record])
    snapshot = service.retrieve_graph_snapshot()
    node_ids = {node.node_id for node in snapshot.nodes}
    edge_types = {edge.edge_type for edge in snapshot.edges}

    assert source_node_id("tx:mar") in node_ids
    assert any(node.node_type == MemoryGraphNodeType.CLAIM for node in snapshot.nodes)
    assert any(node.node_type == MemoryGraphNodeType.SCOPE for node in snapshot.nodes)
    assert MemoryGraphEdgeType.HAS_SUBJECT in edge_types
    assert MemoryGraphEdgeType.HAS_OBJECT in edge_types
    assert MemoryGraphEdgeType.HAS_SCOPE in edge_types
    assert MemoryGraphEdgeType.OBSERVED_IN in edge_types
    assert result.graph_nodes
    assert result.graph_edges
    assert result.graph_validation_errors == []
    assert any(record_id.startswith("mem:evolution:graph-node:") for record_id in result.written_record_ids)
    assert any(record_id.startswith("mem:evolution:graph-edge:") for record_id in result.written_record_ids)


def test_literal_object_claim_uses_literal_object_edge() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    record = _record("tx:status", "Atlas status is failed.", source_kind="tool")

    service.evolve_records([record])

    assert any(
        edge.edge_type == MemoryGraphEdgeType.HAS_LITERAL_OBJECT for edge in service.retrieve_graph_snapshot().edges
    )


def test_action_execution_status_is_independent_of_record_lifecycle() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)

    service.evolve_records([_record("tx:completed", "Atlas completed.", source_kind="tool")])

    action = next(
        node for node in service.retrieve_graph_snapshot().nodes if node.node_type == MemoryGraphNodeType.ACTION
    )
    persisted = plane.get_record(f"mem:evolution:graph-node:{action.node_id}")

    assert action.lifecycle_state == "active"
    assert action.properties["execution_status"] == "completed"
    assert persisted is not None
    assert persisted.validity_status == "active"


def test_graph_validator_rejects_owner_with_non_person_object() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records([_record("tx:owner", "Atlas owner is Bob.")])
    snapshot = service.retrieve_graph_snapshot()
    owner_claim = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.CLAIM
        and node.properties.get("predicate_id") == "owner"
    )
    object_edge = next(
        edge
        for edge in snapshot.edges
        if edge.source_node_id == owner_claim.node_id
        and edge.edge_type == MemoryGraphEdgeType.HAS_OBJECT
    )
    mutated_nodes = [
        node.model_copy(
            update={
                "properties": {
                    **node.properties,
                    "entity_type": "service",
                }
            }
        )
        if node.node_id == object_edge.target_node_id
        else node
        for node in snapshot.nodes
    ]

    errors = MemoryGraphValidator().validate_snapshot(
        snapshot.model_copy(update={"nodes": mutated_nodes})
    )

    assert f"claim_requires_grounded_person_object:{owner_claim.node_id}" in errors


def test_graph_validator_rejects_entity_type_claim_with_entity_object() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records([_record("tx:owner", "Atlas owner is Bob.")])
    snapshot = service.retrieve_graph_snapshot()
    owner_claim = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.CLAIM
        and node.properties.get("predicate_id") == "owner"
    )
    mutated_nodes = [
        node.model_copy(
            update={
                "properties": {
                    **node.properties,
                    "predicate_id": "entity_type",
                }
            }
        )
        if node.node_id == owner_claim.node_id
        else node
        for node in snapshot.nodes
    ]

    errors = MemoryGraphValidator().validate_snapshot(
        snapshot.model_copy(update={"nodes": mutated_nodes})
    )

    assert f"entity_type_claim_has_invalid_endpoints:{owner_claim.node_id}" in errors


def test_graph_validator_rejects_action_without_grounded_target() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records([_record("tx:action", "Atlas completed.", source_kind="tool")])
    snapshot = service.retrieve_graph_snapshot()
    action = next(
        node for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.ACTION
    )
    mutated_edges = [
        edge
        for edge in snapshot.edges
        if not (
            edge.source_node_id == action.node_id
            and edge.edge_type == MemoryGraphEdgeType.HAS_OBJECT
        )
    ]

    errors = MemoryGraphValidator().validate_snapshot(
        snapshot.model_copy(update={"edges": mutated_edges})
    )

    assert f"action_missing_target:{action.node_id}" in errors


def test_graph_validator_rejects_semantic_nodes_and_evidence_edges_without_provenance() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records([_record("tx:status", "Atlas status is active.")])
    snapshot = service.retrieve_graph_snapshot()
    claim = next(
        node for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.CLAIM
    )
    mutated_nodes = [
        node.model_copy(update={"source_record_ids": []})
        if node.node_id == claim.node_id
        else node
        for node in snapshot.nodes
    ]
    mutated_edges = [
        edge.model_copy(
            update={
                "source_record_ids": [],
                "evidence_span_ids": [],
            }
        )
        if edge.source_node_id == claim.node_id
        and edge.edge_type == MemoryGraphEdgeType.OBSERVED_IN
        else edge
        for edge in snapshot.edges
    ]

    errors = MemoryGraphValidator().validate_snapshot(
        snapshot.model_copy(update={"nodes": mutated_nodes, "edges": mutated_edges})
    )

    assert f"semantic_node_missing_provenance:{claim.node_id}" in errors
    assert any(error.startswith("observed_in_missing_provenance:") for error in errors)


def test_graph_validator_rejects_ambiguous_claim_endpoints() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records([_record("tx:owner", "Atlas owner is Bob.")])
    snapshot = service.retrieve_graph_snapshot()
    owner_claim = next(
        node
        for node in snapshot.nodes
        if node.node_type == MemoryGraphNodeType.CLAIM
        and node.properties.get("predicate_id") == "owner"
    )
    endpoint_edges = [
        edge
        for edge in snapshot.edges
        if edge.source_node_id == owner_claim.node_id
        and edge.edge_type
        in {
            MemoryGraphEdgeType.HAS_SUBJECT,
            MemoryGraphEdgeType.HAS_SCOPE,
            MemoryGraphEdgeType.HAS_OBJECT,
        }
    ]
    duplicate_edges = [
        edge.model_copy(update={"edge_id": f"{edge.edge_id}:duplicate"})
        for edge in endpoint_edges
    ]

    errors = MemoryGraphValidator().validate_snapshot(
        snapshot.model_copy(update={"edges": [*snapshot.edges, *duplicate_edges]})
    )

    assert f"claim_ambiguous_subject:{owner_claim.node_id}" in errors
    assert f"claim_ambiguous_scope:{owner_claim.node_id}" in errors
    assert f"claim_ambiguous_object:{owner_claim.node_id}" in errors


def test_superseded_claim_history_is_retained_in_graph() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    jan = _record("tx:jan", "Atlas owner is Alice.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))
    mar = _record("tx:mar", "Atlas owner is Bob.", timestamp=datetime(2026, 3, 1, tzinfo=UTC))

    service.evolve_records([jan])
    service.evolve_records([mar])

    snapshot = service.retrieve_graph_snapshot()
    claim_nodes = [node for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.CLAIM]
    alice_claims = [node for node in claim_nodes if node.properties.get("object_value") == "Alice"]
    bob_claims = [node for node in claim_nodes if node.properties.get("object_value") == "Bob"]

    assert [node.lifecycle_state for node in alice_claims] == ["superseded"]
    assert [node.lifecycle_state for node in bob_claims] == ["active"]
    assert any(edge.edge_type == MemoryGraphEdgeType.SUPERSEDES for edge in snapshot.edges)
    assert any(edge.edge_type == MemoryGraphEdgeType.CONFLICTS_WITH for edge in snapshot.edges)


def test_current_truth_graph_excludes_superseded_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)

    service.evolve_records([_record("tx:jan", "Atlas owner is Alice.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))])
    service.evolve_records([_record("tx:mar", "Atlas owner is Bob.", timestamp=datetime(2026, 3, 1, tzinfo=UTC))])

    current = service.retrieve_current_truth_graph(predicate_id="owner", subject_entity_id="ent:atlas")
    claim_values = [
        node.properties.get("object_value") for node in current.nodes if node.node_type == MemoryGraphNodeType.CLAIM
    ]

    assert claim_values == ["Bob"]


def test_entity_subgraph_can_include_historical_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)

    service.evolve_records([_record("tx:jan", "Atlas owner is Alice.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))])
    service.evolve_records([_record("tx:mar", "Atlas owner is Bob.", timestamp=datetime(2026, 3, 1, tzinfo=UTC))])

    current = service.retrieve_entity_subgraph("ent:atlas")
    historical = service.retrieve_entity_subgraph("ent:atlas", include_historical=True)

    current_values = {
        node.properties.get("object_value") for node in current.nodes if node.node_type == MemoryGraphNodeType.CLAIM
    }
    historical_values = {
        node.properties.get("object_value") for node in historical.nodes if node.node_type == MemoryGraphNodeType.CLAIM
    }
    assert current_values == {"Bob"}
    assert historical_values == {"Alice", "Bob"}


def test_conflict_graph_includes_contradiction_set_and_member_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)

    service.evolve_records([_record("tx:jan", "Atlas owner is Alice.", timestamp=datetime(2026, 1, 1, tzinfo=UTC))])
    service.evolve_records([_record("tx:mar", "Atlas owner is Bob.", timestamp=datetime(2026, 3, 1, tzinfo=UTC))])

    conflict = service.retrieve_conflict_graph()

    assert any(node.node_type == MemoryGraphNodeType.CONTRADICTION_SET for node in conflict.nodes)
    assert any(node.node_type == MemoryGraphNodeType.CLAIM for node in conflict.nodes)
    assert any(edge.edge_type == MemoryGraphEdgeType.MEMBER_OF_CONTRADICTION_SET for edge in conflict.edges)


def test_projection_ids_are_idempotent_across_repeated_evolution_inputs() -> None:
    first_plane = MemoryPlaneService()
    second_plane = MemoryPlaneService()
    first_service = MemoryEvolutionService(memory_plane=first_plane)
    second_service = MemoryEvolutionService(memory_plane=second_plane)
    record = _record("tx:mar", "Atlas owner is Bob.", timestamp=datetime(2026, 3, 1, tzinfo=UTC))

    first_service.evolve_records([record])
    second_service.evolve_records([record])

    assert {node.node_id for node in first_service.retrieve_graph_snapshot().nodes} == {
        node.node_id for node in second_service.retrieve_graph_snapshot().nodes
    }
    assert {edge.edge_id for edge in first_service.retrieve_graph_snapshot().edges} == {
        edge.edge_id for edge in second_service.retrieve_graph_snapshot().edges
    }


def test_graph_validator_reports_exact_missing_endpoint_and_claim_shape_errors() -> None:
    claim_node = MemoryGraphNode(
        node_id=claim_node_id("claim:bad"),
        node_type=MemoryGraphNodeType.CLAIM,
        label="bad claim",
        canonical_id="claim:bad",
        lifecycle_state="active",
        confidence=0.8,
        payload_ref="mem:evolution:claim:claim:bad",
        properties={"claim_id": "claim:bad"},
    )
    bad_edge = MemoryGraphEdge(
        edge_id=edge_id(
            MemoryGraphEdgeType.HAS_SUBJECT,
            claim_node.node_id,
            entity_node_id("missing"),
        ),
        edge_type=MemoryGraphEdgeType.HAS_SUBJECT,
        source_node_id=claim_node.node_id,
        target_node_id=entity_node_id("missing"),
        lifecycle_state="active",
        confidence=0.8,
    )
    snapshot = MemoryGraphSnapshot(snapshot_id="graph:snapshot:test", nodes=[claim_node], edges=[bad_edge])

    errors = MemoryGraphValidator().validate_snapshot(snapshot)

    assert f"missing_endpoint:{bad_edge.edge_id}:{entity_node_id('missing')}" in errors
    assert f"claim_missing_scope:{claim_node.node_id}" in errors
    assert f"claim_missing_object:{claim_node.node_id}" in errors
    assert f"claim_missing_observed_in:{claim_node.node_id}" in errors


def test_graph_validator_rejects_semantic_self_relations() -> None:
    claim_node = MemoryGraphNode(
        node_id=claim_node_id("claim:self"),
        node_type=MemoryGraphNodeType.CLAIM,
        label="self relation claim",
        canonical_id="claim:self",
        lifecycle_state="active",
        confidence=0.8,
        payload_ref="mem:evolution:claim:claim:self",
        properties={"claim_id": "claim:self"},
    )
    self_edge = MemoryGraphEdge(
        edge_id=edge_id(
            MemoryGraphEdgeType.CONTRADICTS,
            claim_node.node_id,
            claim_node.node_id,
        ),
        edge_type=MemoryGraphEdgeType.CONTRADICTS,
        source_node_id=claim_node.node_id,
        target_node_id=claim_node.node_id,
        lifecycle_state="active",
        confidence=0.8,
    )
    snapshot = MemoryGraphSnapshot(
        snapshot_id="graph:snapshot:self",
        nodes=[claim_node],
        edges=[self_edge],
    )

    errors = MemoryGraphValidator().validate_snapshot(snapshot)

    assert f"self_relation:{self_edge.edge_id}" in errors
