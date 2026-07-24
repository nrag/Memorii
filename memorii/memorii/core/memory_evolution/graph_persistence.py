"""Memory-plane persistence and structural validation for graph snapshots."""

from pydantic import ValidationError

from memorii.core.memory_evolution.graph_ids import stable_graph_id
from memorii.core.memory_evolution.models import (
    MemoryGraphEdge,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    RecordLifecycleState,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus


class MemoryGraphStore:
    def __init__(self, *, memory_plane: MemoryPlaneService) -> None:
        self._memory_plane = memory_plane
        self._read_diagnostics: dict[str, int] = {
            "skipped_node_count": 0,
            "skipped_edge_count": 0,
        }

    @property
    def read_diagnostics(self) -> dict[str, int]:
        return dict(self._read_diagnostics)

    def upsert_snapshot(self, snapshot: MemoryGraphSnapshot) -> list[str]:
        records = [
            *(_record_from_graph_node(node) for node in snapshot.nodes),
            *(_record_from_graph_edge(edge) for edge in snapshot.edges),
        ]
        for record in records:
            self._memory_plane.upsert_record(record)
        return [record.memory_id for record in records]

    def list_nodes(self, *, node_type: MemoryGraphNodeType | None = None) -> list[MemoryGraphNode]:
        nodes: list[MemoryGraphNode] = []
        for record in self._memory_plane.list_records(
            domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EXECUTION]
        ):
            if record.content.get("memory_evolution_kind") != "graph_node":
                continue
            try:
                node = MemoryGraphNode.model_validate(record.content["graph_node"])
            except ValidationError:
                self._read_diagnostics["skipped_node_count"] += 1
                continue
            if node_type is None or node.node_type == node_type:
                nodes.append(node)
        return sorted(nodes, key=lambda item: item.node_id)

    def list_edges(self, *, edge_type: MemoryGraphEdgeType | None = None) -> list[MemoryGraphEdge]:
        edges: list[MemoryGraphEdge] = []
        for record in self._memory_plane.list_records(
            domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EXECUTION]
        ):
            if record.content.get("memory_evolution_kind") != "graph_edge":
                continue
            try:
                edge = MemoryGraphEdge.model_validate(record.content["graph_edge"])
            except ValidationError:
                self._read_diagnostics["skipped_edge_count"] += 1
                continue
            if edge_type is None or edge.edge_type == edge_type:
                edges.append(edge)
        return sorted(edges, key=lambda item: item.edge_id)

    def snapshot(self) -> MemoryGraphSnapshot:
        self._read_diagnostics = {"skipped_node_count": 0, "skipped_edge_count": 0}
        nodes = self.list_nodes()
        edges = self.list_edges()
        return MemoryGraphSnapshot(
            snapshot_id=stable_graph_id(
                "graph:snapshot",
                "|".join([*(node.node_id for node in nodes), *(edge.edge_id for edge in edges)]),
            ),
            nodes=nodes,
            edges=edges,
            validation_errors=[
                f"{key}={value}"
                for key, value in sorted(self._read_diagnostics.items())
                if value
            ],
        )


class MemoryGraphValidator:
    def validate_snapshot(self, snapshot: MemoryGraphSnapshot) -> list[str]:
        node_by_id = {node.node_id: node for node in snapshot.nodes}
        errors: list[str] = []
        for edge in snapshot.edges:
            if (
                edge.source_node_id == edge.target_node_id
                and edge.edge_type
                in {
                    MemoryGraphEdgeType.SUPERSEDES,
                    MemoryGraphEdgeType.CONFLICTS_WITH,
                    MemoryGraphEdgeType.CONTRADICTS,
                    MemoryGraphEdgeType.MERGED_INTO,
                    MemoryGraphEdgeType.SPLIT_FROM,
                    MemoryGraphEdgeType.REKEYED_FROM,
                }
            ):
                errors.append(f"self_relation:{edge.edge_id}")
            if edge.source_node_id not in node_by_id:
                errors.append(f"missing_endpoint:{edge.edge_id}:{edge.source_node_id}")
            if edge.target_node_id not in node_by_id:
                errors.append(f"missing_endpoint:{edge.edge_id}:{edge.target_node_id}")
            if edge.edge_type == MemoryGraphEdgeType.OBSERVED_IN:
                target = node_by_id.get(edge.target_node_id)
                if target is not None and target.node_type != MemoryGraphNodeType.SOURCE_OBSERVATION:
                    errors.append(f"invalid_observed_in_target:{edge.edge_id}")
            if edge.edge_type in {
                MemoryGraphEdgeType.SUPERSEDES,
                MemoryGraphEdgeType.CONFLICTS_WITH,
                MemoryGraphEdgeType.CONTRADICTS,
            }:
                _validate_edge_node_type(
                    edge=edge,
                    node_by_id=node_by_id,
                    expected_type=MemoryGraphNodeType.CLAIM,
                    errors=errors,
                )
            if edge.edge_type in {MemoryGraphEdgeType.MERGED_INTO, MemoryGraphEdgeType.SPLIT_FROM}:
                _validate_edge_node_type(
                    edge=edge,
                    node_by_id=node_by_id,
                    expected_type=MemoryGraphNodeType.ENTITY,
                    errors=errors,
                )
            if edge.edge_type == MemoryGraphEdgeType.REKEYED_FROM:
                for endpoint_id in (edge.source_node_id, edge.target_node_id):
                    endpoint = node_by_id.get(endpoint_id)
                    if endpoint is not None and endpoint.node_type != MemoryGraphNodeType.CLAIM:
                        errors.append(f"invalid_rekey_endpoint:{edge.edge_id}")
        edges_by_source: dict[str, list[MemoryGraphEdge]] = {}
        for edge in snapshot.edges:
            edges_by_source.setdefault(edge.source_node_id, []).append(edge)
        for node in snapshot.nodes:
            if node.node_type != MemoryGraphNodeType.CLAIM or node.lifecycle_state == RecordLifecycleState.CANDIDATE:
                continue
            edge_types = {edge.edge_type for edge in edges_by_source.get(node.node_id, [])}
            if MemoryGraphEdgeType.HAS_SUBJECT not in edge_types:
                errors.append(f"claim_missing_subject:{node.node_id}")
            if MemoryGraphEdgeType.HAS_SCOPE not in edge_types:
                errors.append(f"claim_missing_scope:{node.node_id}")
            if not ({MemoryGraphEdgeType.HAS_OBJECT, MemoryGraphEdgeType.HAS_LITERAL_OBJECT} & edge_types):
                errors.append(f"claim_missing_object:{node.node_id}")
            if MemoryGraphEdgeType.OBSERVED_IN not in edge_types:
                errors.append(f"claim_missing_observed_in:{node.node_id}")
        return sorted(set(errors))


def _validate_edge_node_type(
    *,
    edge: MemoryGraphEdge,
    node_by_id: dict[str, MemoryGraphNode],
    expected_type: MemoryGraphNodeType,
    errors: list[str],
) -> None:
    for endpoint_id in (edge.source_node_id, edge.target_node_id):
        endpoint = node_by_id.get(endpoint_id)
        if endpoint is not None and endpoint.node_type != expected_type:
            errors.append(_invalid_edge_error(edge))


def _record_from_graph_node(node: MemoryGraphNode) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:graph-node:{node.node_id}",
        domain=_domain_for_graph_node(node),
        text=f"{node.node_type.value}: {node.label}",
        content={"memory_evolution_kind": "graph_node", "graph_node": node.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        validity_status=_validity_for_lifecycle(node.lifecycle_state),
        source_kind="memory_evolution_graph",
        timestamp=node.updated_at,
        is_raw_event=False,
        source_candidate_id=node.payload_ref,
    )


def _record_from_graph_edge(edge: MemoryGraphEdge) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:graph-edge:{edge.edge_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"{edge.source_node_id} {edge.edge_type.value} {edge.target_node_id}",
        content={"memory_evolution_kind": "graph_edge", "graph_edge": edge.model_dump(mode="json")},
        status=CommitStatus.COMMITTED,
        validity_status=_validity_for_lifecycle(edge.lifecycle_state),
        source_kind="memory_evolution_graph",
        timestamp=edge.updated_at,
        is_raw_event=False,
        source_candidate_id=edge.source_record_ids[0] if edge.source_record_ids else None,
    )


def _domain_for_graph_node(node: MemoryGraphNode) -> MemoryDomain:
    if node.node_type in {MemoryGraphNodeType.ACTION, MemoryGraphNodeType.TASK}:
        return MemoryDomain.EXECUTION
    if node.node_type == MemoryGraphNodeType.CLAIM and node.properties.get("predicate_id") == "preference":
        return MemoryDomain.USER
    return MemoryDomain.SEMANTIC


def _validity_for_lifecycle(lifecycle_state: RecordLifecycleState) -> TemporalValidityStatus:
    return {
        RecordLifecycleState.ACTIVE: TemporalValidityStatus.ACTIVE,
        RecordLifecycleState.CANDIDATE: TemporalValidityStatus.UNKNOWN,
        RecordLifecycleState.SUPERSEDED: TemporalValidityStatus.INVALIDATED,
        RecordLifecycleState.INVALIDATED: TemporalValidityStatus.INVALIDATED,
        RecordLifecycleState.ARCHIVED: TemporalValidityStatus.INVALIDATED,
        RecordLifecycleState.EXPIRED: TemporalValidityStatus.EXPIRED,
        RecordLifecycleState.MERGED: TemporalValidityStatus.INVALIDATED,
        RecordLifecycleState.SPLIT: TemporalValidityStatus.INVALIDATED,
        RecordLifecycleState.RELINKED: TemporalValidityStatus.INVALIDATED,
        RecordLifecycleState.UNKNOWN: TemporalValidityStatus.UNKNOWN,
    }[lifecycle_state]


def _invalid_edge_error(edge: MemoryGraphEdge) -> str:
    labels = {
        MemoryGraphEdgeType.SUPERSEDES: "supersedes",
        MemoryGraphEdgeType.CONFLICTS_WITH: "conflict",
        MemoryGraphEdgeType.CONTRADICTS: "contradicts",
        MemoryGraphEdgeType.MERGED_INTO: "merge",
        MemoryGraphEdgeType.SPLIT_FROM: "split",
    }
    return f"invalid_{labels.get(edge.edge_type, 'rekey')}_endpoint:{edge.edge_id}"
