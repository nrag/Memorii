"""Read-only graph queries over projected memory-evolution state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from memorii.core.memory_evolution.graph import MemoryGraphStore, subgraph_from_ids
from memorii.core.memory_evolution.models import (
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
)
from memorii.core.memory_evolution.temporal_contracts import (
    QueryTemporalFrame,
    QueryTemporalKind,
    evaluate_temporal_eligibility,
)


class MemoryGraphQueryService:
    """Own graph filtering and subgraph expansion without mutating graph state."""

    def __init__(
        self,
        *,
        graph_store: MemoryGraphStore,
        now_provider: Callable[[], datetime],
    ) -> None:
        self._graph_store = graph_store
        self._now_provider = now_provider

    def snapshot(self) -> MemoryGraphSnapshot:
        return self._graph_store.snapshot()

    def current_truth(
        self,
        *,
        subject_entity_id: str | None = None,
        predicate_id: str | None = None,
        temporal_frame: QueryTemporalFrame | None = None,
        evaluation_time: datetime | None = None,
    ) -> MemoryGraphSnapshot:
        frame = temporal_frame or QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            evaluation_time=evaluation_time,
        )
        if (
            frame.temporal_kind
            in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}
            and frame.evaluation_time is None
        ):
            frame = frame.model_copy(update={"evaluation_time": self._now_provider()})
        snapshot = self.snapshot()
        matching_claims = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CLAIM
            and graph_claim_matches_frame(node=node, frame=frame)
            and (predicate_id is None or node.properties.get("predicate_id") == predicate_id)
            and (subject_entity_id is None or node.properties.get("subject_entity_id") == subject_entity_id)
        }
        return claim_subgraph(
            snapshot=snapshot,
            claim_node_ids=matching_claims,
            include_edge_types={
                MemoryGraphEdgeType.HAS_SUBJECT,
                MemoryGraphEdgeType.HAS_OBJECT,
                MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
                MemoryGraphEdgeType.HAS_SCOPE,
                MemoryGraphEdgeType.OBSERVED_IN,
            },
        )

    def entity_subgraph(
        self,
        entity_id: str,
        *,
        include_historical: bool = False,
        include_conflicts: bool = False,
        temporal_frame: QueryTemporalFrame | None = None,
        evaluation_time: datetime | None = None,
    ) -> MemoryGraphSnapshot:
        frame = temporal_frame
        if frame is None and evaluation_time is not None:
            frame = QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.HISTORICAL if include_historical else QueryTemporalKind.CURRENT,
                evaluation_time=None if include_historical else evaluation_time,
                valid_from=evaluation_time if include_historical else None,
                valid_to=(evaluation_time + timedelta(microseconds=1)) if include_historical else None,
            )
        if frame is None and not include_historical:
            frame = QueryTemporalFrame(temporal_kind=QueryTemporalKind.CURRENT, evaluation_time=self._now_provider())
        elif (
            frame is not None
            and frame.temporal_kind
            in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}
            and frame.evaluation_time is None
        ):
            frame = frame.model_copy(update={"evaluation_time": self._now_provider()})
        snapshot = self.snapshot()
        node_by_id = {node.node_id: node for node in snapshot.nodes}
        entity_node_ids = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.ENTITY
            and (node.node_id == entity_id or node.canonical_id == entity_id)
        }
        claim_node_ids: set[str] = set()
        edge_ids: set[str] = set()
        for edge in snapshot.edges:
            if edge.edge_type == MemoryGraphEdgeType.ALIAS_OF and edge.source_node_id in entity_node_ids:
                edge_ids.add(edge.edge_id)
            if edge.edge_type not in {MemoryGraphEdgeType.HAS_SUBJECT, MemoryGraphEdgeType.HAS_OBJECT}:
                continue
            if edge.target_node_id not in entity_node_ids:
                continue
            claim = node_by_id.get(edge.source_node_id)
            if claim is None or claim.node_type != MemoryGraphNodeType.CLAIM:
                continue
            if frame is None or graph_claim_matches_frame(node=claim, frame=frame):
                claim_node_ids.add(claim.node_id)
        claim_graph = claim_subgraph(
            snapshot=snapshot,
            claim_node_ids=claim_node_ids,
            include_edge_types={
                MemoryGraphEdgeType.HAS_SUBJECT,
                MemoryGraphEdgeType.HAS_OBJECT,
                MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
                MemoryGraphEdgeType.HAS_SCOPE,
                MemoryGraphEdgeType.OBSERVED_IN,
            },
        )
        node_ids = {node.node_id for node in claim_graph.nodes} | entity_node_ids
        edge_ids |= {edge.edge_id for edge in claim_graph.edges}
        if include_conflicts:
            for edge in snapshot.edges:
                if edge.edge_type in {
                    MemoryGraphEdgeType.CONFLICTS_WITH,
                    MemoryGraphEdgeType.CONTRADICTS,
                    MemoryGraphEdgeType.MEMBER_OF_CONTRADICTION_SET,
                } and (edge.source_node_id in node_ids or edge.target_node_id in node_ids):
                    edge_ids.add(edge.edge_id)
                    node_ids.add(edge.source_node_id)
                    node_ids.add(edge.target_node_id)
        return subgraph_from_ids(snapshot=snapshot, node_ids=node_ids, edge_ids=edge_ids)

    def claim_lineage(self, claim_id: str) -> MemoryGraphSnapshot:
        snapshot = self.snapshot()
        claim_node_ids = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CLAIM
            and (node.node_id == claim_id or node.canonical_id == claim_id)
        }
        return claim_subgraph(
            snapshot=snapshot,
            claim_node_ids=claim_node_ids,
            include_edge_types={
                MemoryGraphEdgeType.HAS_SUBJECT,
                MemoryGraphEdgeType.HAS_OBJECT,
                MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
                MemoryGraphEdgeType.HAS_SCOPE,
                MemoryGraphEdgeType.OBSERVED_IN,
                MemoryGraphEdgeType.SUPERSEDES,
                MemoryGraphEdgeType.CONFLICTS_WITH,
                MemoryGraphEdgeType.CONTRADICTS,
            },
        )

    def conflict_graph(self) -> MemoryGraphSnapshot:
        snapshot = self.snapshot()
        node_ids = {
            node.node_id for node in snapshot.nodes if node.node_type == MemoryGraphNodeType.CONTRADICTION_SET
        }
        edge_ids: set[str] = set()
        for edge in snapshot.edges:
            if edge.edge_type in {
                MemoryGraphEdgeType.MEMBER_OF_CONTRADICTION_SET,
                MemoryGraphEdgeType.CONTRADICTS,
                MemoryGraphEdgeType.CONFLICTS_WITH,
            } and (edge.source_node_id in node_ids or edge.target_node_id in node_ids):
                edge_ids.add(edge.edge_id)
                node_ids.add(edge.source_node_id)
                node_ids.add(edge.target_node_id)
        for edge in snapshot.edges:
            if edge.edge_type == MemoryGraphEdgeType.OBSERVED_IN and edge.source_node_id in node_ids:
                edge_ids.add(edge.edge_id)
                node_ids.add(edge.target_node_id)
        return subgraph_from_ids(snapshot=snapshot, node_ids=node_ids, edge_ids=edge_ids)


def graph_claim_matches_frame(*, node: MemoryGraphNode, frame: QueryTemporalFrame) -> bool:
    properties = node.properties
    if frame.resolved_entity_ids:
        resolved_entity_ids = set(frame.resolved_entity_ids)
        if not (
            {
                properties.get("subject_entity_id", ""),
                properties.get("object_entity_id", ""),
                properties.get("object_link_id", ""),
            }
            & resolved_entity_ids
        ):
            return False
    if frame.scope_key is not None and properties.get("scope_key") not in {frame.scope_key, "global"}:
        return False
    if frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        return evaluate_temporal_eligibility(
            lifecycle_state=node.lifecycle_state,
            valid_from=parse_graph_datetime(properties.get("valid_from")),
            valid_to=parse_graph_datetime(properties.get("valid_to")),
            temporal_kind=frame.temporal_kind,
            evaluation_time=frame.evaluation_time,
        ).eligible
    if frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        return evaluate_temporal_eligibility(
            lifecycle_state=node.lifecycle_state,
            valid_from=parse_graph_datetime(properties.get("valid_from")),
            valid_to=parse_graph_datetime(properties.get("valid_to")),
            temporal_kind=frame.temporal_kind,
            requested_from=frame.valid_from,
            requested_to=frame.valid_to,
        ).eligible
    return False


def parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def claim_subgraph(
    *,
    snapshot: MemoryGraphSnapshot,
    claim_node_ids: set[str],
    include_edge_types: set[MemoryGraphEdgeType],
) -> MemoryGraphSnapshot:
    node_ids = set(claim_node_ids)
    edge_ids: set[str] = set()
    for edge in snapshot.edges:
        if edge.edge_type not in include_edge_types:
            continue
        if edge.source_node_id in claim_node_ids or edge.target_node_id in claim_node_ids:
            edge_ids.add(edge.edge_id)
            node_ids.add(edge.source_node_id)
            node_ids.add(edge.target_node_id)
    return subgraph_from_ids(snapshot=snapshot, node_ids=node_ids, edge_ids=edge_ids)
