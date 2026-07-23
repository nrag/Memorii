"""Runtime graph projection over evolved memory state."""

from __future__ import annotations

from memorii.core.memory_evolution.execution import normalize_work_state_status
from memorii.core.memory_evolution.graph_ids import (
    action_node_id,
    candidate_entity_node_id,
    claim_node_id,
    contradiction_node_id,
    edge_id,
    entity_node_id,
    literal_node_id,
    normalize_value,
    scope_node_id,
    source_node_id,
    stable_graph_id,
    task_node_id,
)
from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    ClaimTransitionType,
    ContradictionSet,
    EntityLinkLifecycleState,
    EntityLinkState,
    EvidenceSpan,
    ExtractedAction,
    MemoryEvolutionResult,
    MemoryGraphEdge,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    MemoryScope,
    RecordLifecycleState,
    SourceObservation,
)
from memorii.core.memory_plane.service import MemoryPlaneService


class MemoryGraphProjector:
    def project_evolution_result(
        self,
        *,
        result: MemoryEvolutionResult,
        existing_snapshot: MemoryGraphSnapshot | None = None,
    ) -> MemoryGraphSnapshot:
        del existing_snapshot
        node_by_id: dict[str, MemoryGraphNode] = {}
        edge_by_id: dict[str, MemoryGraphEdge] = {}
        source_by_id = {observation.source_id: observation for observation in result.observations}
        link_by_id = {link.link_id: link for link in result.entity_links}

        for observation in result.observations:
            self._add_source_observation(node_by_id, observation)
        for link in result.entity_links:
            self._add_entity_link(node_by_id, edge_by_id, link)
        for state in result.claim_states:
            self._add_claim_state(node_by_id, edge_by_id, state, link_by_id, source_by_id)
        for action in result.actions:
            self._add_action(node_by_id, edge_by_id, action, source_by_id)
        for contradiction_set in result.contradiction_sets:
            self._add_contradiction_set(node_by_id, edge_by_id, contradiction_set)
        for transition in result.transitions:
            self._add_lifecycle_transition(node_by_id, edge_by_id, transition)

        nodes = sorted(node_by_id.values(), key=lambda item: item.node_id)
        edges = sorted(edge_by_id.values(), key=lambda item: item.edge_id)
        snapshot_id = stable_graph_id(
            "graph:snapshot",
            "|".join([*(node.node_id for node in nodes), *(edge.edge_id for edge in edges)]),
        )
        return MemoryGraphSnapshot(
            snapshot_id=snapshot_id,
            nodes=nodes,
            edges=edges,
            source_run_id=result.extraction_run.extraction_run_id,
        )

    def _add_lifecycle_transition(
        self,
        node_by_id: dict[str, MemoryGraphNode],
        edge_by_id: dict[str, MemoryGraphEdge],
        transition: ClaimLifecycleTransition,
    ) -> None:
        # Entity split lineage is projected from the persisted child
        # EntityLinkState. Emitting a second transition edge would create two
        # runtime relations for one semantic split and break one-to-one audit
        # alignment after the transition event has passed.
        if transition.transition_type == ClaimTransitionType.ENTITY_SPLIT:
            return
        if transition.transition_type == ClaimTransitionType.CLAIM_REKEY and transition.related_claim_ids:
            source = claim_node_id(transition.claim_id)
            target = claim_node_id(transition.related_claim_ids[0])
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.REKEYED_FROM,
                source,
                target,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=0.8,
                properties={"transition_id": transition.transition_id},
            )

    def project_from_memory_plane(self, *, memory_plane: MemoryPlaneService) -> MemoryGraphSnapshot:
        from memorii.core.memory_evolution.graph_persistence import MemoryGraphStore

        return MemoryGraphStore(memory_plane=memory_plane).snapshot()

    def nodes_and_edges_for_source_observation(
        self,
        observation: SourceObservation,
    ) -> tuple[list[MemoryGraphNode], list[MemoryGraphEdge]]:
        node_by_id: dict[str, MemoryGraphNode] = {}
        self._add_source_observation(node_by_id, observation)
        return list(node_by_id.values()), []

    def nodes_and_edges_for_entity_link(
        self,
        link: EntityLinkState,
    ) -> tuple[list[MemoryGraphNode], list[MemoryGraphEdge]]:
        node_by_id: dict[str, MemoryGraphNode] = {}
        edge_by_id: dict[str, MemoryGraphEdge] = {}
        self._add_entity_link(node_by_id, edge_by_id, link)
        return list(node_by_id.values()), list(edge_by_id.values())

    def nodes_and_edges_for_claim_state(
        self,
        state: ClaimState,
    ) -> tuple[list[MemoryGraphNode], list[MemoryGraphEdge]]:
        node_by_id: dict[str, MemoryGraphNode] = {}
        edge_by_id: dict[str, MemoryGraphEdge] = {}
        self._add_claim_state(node_by_id, edge_by_id, state, {}, {})
        return list(node_by_id.values()), list(edge_by_id.values())

    def nodes_and_edges_for_action(
        self,
        action: ExtractedAction,
    ) -> tuple[list[MemoryGraphNode], list[MemoryGraphEdge]]:
        node_by_id: dict[str, MemoryGraphNode] = {}
        edge_by_id: dict[str, MemoryGraphEdge] = {}
        self._add_action(node_by_id, edge_by_id, action, {})
        return list(node_by_id.values()), list(edge_by_id.values())

    def nodes_and_edges_for_contradiction_set(
        self,
        contradiction_set: ContradictionSet,
    ) -> tuple[list[MemoryGraphNode], list[MemoryGraphEdge]]:
        node_by_id: dict[str, MemoryGraphNode] = {}
        edge_by_id: dict[str, MemoryGraphEdge] = {}
        self._add_contradiction_set(node_by_id, edge_by_id, contradiction_set)
        return list(node_by_id.values()), list(edge_by_id.values())

    def _add_source_observation(
        self,
        node_by_id: dict[str, MemoryGraphNode],
        observation: SourceObservation,
    ) -> MemoryGraphNode:
        node_id = source_node_id(observation.source_id)
        node = MemoryGraphNode(
            node_id=node_id,
            node_type=MemoryGraphNodeType.SOURCE_OBSERVATION,
            label=observation.text[:80],
            canonical_id=observation.source_id,
            lifecycle_state=RecordLifecycleState.ACTIVE,
            confidence=1.0,
            source_record_ids=[observation.source_id],
            payload_ref=observation.source_id,
            properties={
                "source_type": observation.source_type.value,
                "modality": observation.modality.value,
                "trigger_mode": observation.trigger_mode.value,
                "domain": observation.domain.value,
                "session_id": observation.session_id or "",
                "task_id": observation.task_id or "",
                "user_id": observation.user_id or "",
            },
            created_at=observation.timestamp,
            updated_at=observation.timestamp,
        )
        node_by_id[node_id] = node
        return node

    def _add_entity_link(
        self,
        node_by_id: dict[str, MemoryGraphNode],
        edge_by_id: dict[str, MemoryGraphEdge],
        link: EntityLinkState,
    ) -> MemoryGraphNode:
        node = _node_from_entity_link(link)
        node_by_id[node.node_id] = node
        for alias in link.aliases:
            alias_node = _literal_node(alias, lifecycle_state=link.lifecycle_state, confidence=link.confidence)
            node_by_id.setdefault(alias_node.node_id, alias_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.ALIAS_OF,
                node.node_id,
                alias_node.node_id,
                lifecycle_state=link.lifecycle_state,
                confidence=link.confidence,
            )
        if link.lifecycle_state == EntityLinkLifecycleState.MERGED and link.superseded_by_entity_id:
            target_node = _candidate_entity_node(link.superseded_by_entity_id)
            node_by_id.setdefault(target_node.node_id, target_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.MERGED_INTO,
                node.node_id,
                target_node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=link.confidence,
            )
        if link.lineage_parent_entity_id:
            parent_node = _candidate_entity_node(link.lineage_parent_entity_id)
            node_by_id.setdefault(parent_node.node_id, parent_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.SPLIT_FROM,
                node.node_id,
                parent_node.node_id,
                lifecycle_state=link.lifecycle_state,
                confidence=link.confidence,
            )
        return node

    def _add_claim_state(
        self,
        node_by_id: dict[str, MemoryGraphNode],
        edge_by_id: dict[str, MemoryGraphEdge],
        state: ClaimState,
        link_by_id: dict[str, EntityLinkState],
        source_by_id: dict[str, SourceObservation],
    ) -> MemoryGraphNode:
        claim_node = _node_from_claim_state(state)
        node_by_id[claim_node.node_id] = claim_node
        subject_node = _entity_node_for_claim_subject(state, link_by_id)
        node_by_id.setdefault(subject_node.node_id, subject_node)
        self._add_edge(
            edge_by_id,
            MemoryGraphEdgeType.HAS_SUBJECT,
            claim_node.node_id,
            subject_node.node_id,
            lifecycle_state=state.lifecycle_state,
            confidence=state.confidence.calibrated,
        )

        if state.object_link_id and state.object_link_id in link_by_id:
            object_node = _node_from_entity_link(link_by_id[state.object_link_id])
            node_by_id.setdefault(object_node.node_id, object_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.HAS_OBJECT,
                claim_node.node_id,
                object_node.node_id,
                lifecycle_state=state.lifecycle_state,
                confidence=state.confidence.calibrated,
            )
        else:
            literal_node = _literal_node(
                state.object_value, lifecycle_state=state.lifecycle_state, confidence=state.confidence.calibrated
            )
            node_by_id.setdefault(literal_node.node_id, literal_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
                claim_node.node_id,
                literal_node.node_id,
                lifecycle_state=state.lifecycle_state,
                confidence=state.confidence.calibrated,
            )

        scope_node = _scope_node(state.claim_key.scope)
        node_by_id.setdefault(scope_node.node_id, scope_node)
        self._add_edge(
            edge_by_id,
            MemoryGraphEdgeType.HAS_SCOPE,
            claim_node.node_id,
            scope_node.node_id,
            lifecycle_state=state.lifecycle_state,
            confidence=state.confidence.calibrated,
        )

        for span in state.evidence_spans:
            source_node = _source_node_from_span(span, source_by_id)
            node_by_id.setdefault(source_node.node_id, source_node)
            span_id = _span_id(span)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.OBSERVED_IN,
                claim_node.node_id,
                source_node.node_id,
                lifecycle_state=state.lifecycle_state,
                confidence=state.confidence.evidence,
                evidence_span_ids=[span_id],
                source_record_ids=[span.source_id],
            )
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.MENTIONS,
                source_node.node_id,
                subject_node.node_id,
                lifecycle_state=state.lifecycle_state,
                confidence=state.confidence.evidence,
                evidence_span_ids=[span_id],
                source_record_ids=[span.source_id],
            )

        for old_claim_id in state.supersedes_claim_ids:
            self._add_claim_placeholder(node_by_id, old_claim_id)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.SUPERSEDES,
                claim_node.node_id,
                claim_node_id(old_claim_id),
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=state.confidence.calibrated,
            )
        if state.superseded_by_claim_id:
            self._add_claim_placeholder(node_by_id, state.superseded_by_claim_id)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.SUPERSEDES,
                claim_node_id(state.superseded_by_claim_id),
                claim_node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=state.confidence.calibrated,
            )
        for conflict_claim_id in state.conflict_with_claim_ids:
            self._add_claim_placeholder(node_by_id, conflict_claim_id)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.CONFLICTS_WITH,
                claim_node.node_id,
                claim_node_id(conflict_claim_id),
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=state.confidence.calibrated,
            )
        return claim_node

    def _add_action(
        self,
        node_by_id: dict[str, MemoryGraphNode],
        edge_by_id: dict[str, MemoryGraphEdge],
        action: ExtractedAction,
        source_by_id: dict[str, SourceObservation],
    ) -> MemoryGraphNode:
        execution_status = normalize_work_state_status(action.status)
        node = MemoryGraphNode(
            node_id=action_node_id(action.action_id),
            node_type=MemoryGraphNodeType.ACTION,
            label=f"{action.action_type} {action.status}",
            canonical_id=action.action_id,
            lifecycle_state=RecordLifecycleState.ACTIVE,
            confidence=0.8,
            source_record_ids=[span.source_id for span in action.evidence_spans],
            payload_ref=f"mem:evolution:action:{action.action_id}",
            properties={
                "action_id": action.action_id,
                "action_type": action.action_type,
                "status": action.status,
                "execution_status": execution_status.value,
                "timestamp": action.timestamp.isoformat(),
                "actor_entity_id": action.actor_entity_id or "",
                "target_entity_ids": "|".join(action.target_entity_ids),
                "task_id": action.task_id or "",
                "session_id": action.session_id or "",
                "user_id": action.user_id or "",
                "scope_key": action.scope_key,
            },
            created_at=action.timestamp,
            updated_at=action.timestamp,
        )
        node_by_id[node.node_id] = node
        for target_id in action.target_entity_ids:
            target_node = _candidate_entity_node(target_id)
            node_by_id.setdefault(target_node.node_id, target_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.HAS_OBJECT,
                node.node_id,
                target_node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=0.8,
            )
        for dep_id in action.dependency_ids:
            dep_node = _task_node(dep_id)
            node_by_id.setdefault(dep_node.node_id, dep_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.DEPENDS_ON,
                node.node_id,
                dep_node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=0.8,
            )
        for blocking_id in action.blocking_ids:
            blocking_node = _task_node(blocking_id)
            node_by_id.setdefault(blocking_node.node_id, blocking_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.BLOCKS,
                node.node_id,
                blocking_node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=0.8,
            )
        for span in action.evidence_spans:
            source_node = _source_node_from_span(span, source_by_id)
            node_by_id.setdefault(source_node.node_id, source_node)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.OBSERVED_IN,
                node.node_id,
                source_node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=0.8,
                evidence_span_ids=[_span_id(span)],
                source_record_ids=[span.source_id],
            )
        return node

    def _add_contradiction_set(
        self,
        node_by_id: dict[str, MemoryGraphNode],
        edge_by_id: dict[str, MemoryGraphEdge],
        contradiction_set: ContradictionSet,
    ) -> MemoryGraphNode:
        node = MemoryGraphNode(
            node_id=contradiction_node_id(contradiction_set.contradiction_set_id),
            node_type=MemoryGraphNodeType.CONTRADICTION_SET,
            label=f"Contradiction for {contradiction_set.claim_key.stable_id()}",
            canonical_id=contradiction_set.contradiction_set_id,
            lifecycle_state=RecordLifecycleState.ACTIVE,
            confidence=0.8,
            source_record_ids=[],
            payload_ref=f"mem:evolution:contradiction:{contradiction_set.contradiction_set_id}",
            properties={
                "contradiction_set_id": contradiction_set.contradiction_set_id,
                "predicate_id": contradiction_set.predicate_id,
                "claim_key": contradiction_set.claim_key.stable_id(),
                "active_claim_id": contradiction_set.active_claim_id or "",
                "conflicting_claim_ids": "|".join(contradiction_set.conflicting_claim_ids),
            },
            created_at=contradiction_set.created_at,
            updated_at=contradiction_set.updated_at,
        )
        node_by_id[node.node_id] = node
        member_ids = [
            item for item in [contradiction_set.active_claim_id, *contradiction_set.conflicting_claim_ids] if item
        ]
        for member_id in member_ids:
            self._add_claim_placeholder(node_by_id, member_id)
            self._add_edge(
                edge_by_id,
                MemoryGraphEdgeType.MEMBER_OF_CONTRADICTION_SET,
                claim_node_id(member_id),
                node.node_id,
                lifecycle_state=RecordLifecycleState.ACTIVE,
                confidence=0.8,
            )
        if contradiction_set.active_claim_id:
            for conflict_id in contradiction_set.conflicting_claim_ids:
                self._add_edge(
                    edge_by_id,
                    MemoryGraphEdgeType.CONTRADICTS,
                    claim_node_id(contradiction_set.active_claim_id),
                    claim_node_id(conflict_id),
                    lifecycle_state=RecordLifecycleState.ACTIVE,
                    confidence=0.8,
                )
        return node

    def _add_claim_placeholder(self, node_by_id: dict[str, MemoryGraphNode], claim_id: str) -> None:
        node_by_id.setdefault(
            claim_node_id(claim_id),
            MemoryGraphNode(
                node_id=claim_node_id(claim_id),
                node_type=MemoryGraphNodeType.CLAIM,
                label=claim_id,
                canonical_id=claim_id,
                lifecycle_state=RecordLifecycleState.CANDIDATE,
                confidence=0.4,
                payload_ref=f"mem:evolution:claim:{claim_id}",
                properties={"claim_id": claim_id},
            ),
        )

    def _add_edge(
        self,
        edge_by_id: dict[str, MemoryGraphEdge],
        edge_type: MemoryGraphEdgeType,
        source_id: str,
        target_id: str,
        *,
        lifecycle_state: RecordLifecycleState | ClaimLifecycleState | EntityLinkLifecycleState,
        confidence: float,
        evidence_span_ids: list[str] | None = None,
        source_record_ids: list[str] | None = None,
        qualifier: str = "default",
        directed: bool = True,
        properties: dict[str, str] | None = None,
    ) -> MemoryGraphEdge:
        edge = MemoryGraphEdge(
            edge_id=edge_id(edge_type, source_id, target_id, qualifier),
            edge_type=edge_type,
            source_node_id=source_id,
            target_node_id=target_id,
            directed=directed,
            lifecycle_state=_graph_lifecycle_state(lifecycle_state),
            confidence=confidence,
            evidence_span_ids=evidence_span_ids or [],
            source_record_ids=source_record_ids or [],
            properties=properties or {},
        )
        edge_by_id[edge.edge_id] = edge
        return edge


def subgraph_from_ids(
    *,
    snapshot: MemoryGraphSnapshot,
    node_ids: set[str],
    edge_ids: set[str] | None = None,
) -> MemoryGraphSnapshot:
    edge_ids = edge_ids or set()
    expanded_ids = set(node_ids)
    edges: list[MemoryGraphEdge] = []
    for edge in snapshot.edges:
        if edge.edge_id in edge_ids:
            edges.append(edge)
            expanded_ids.add(edge.source_node_id)
            expanded_ids.add(edge.target_node_id)
    nodes = [node for node in snapshot.nodes if node.node_id in expanded_ids]
    return MemoryGraphSnapshot(
        snapshot_id=stable_graph_id("graph:snapshot", "|".join(sorted(expanded_ids))),
        nodes=sorted(nodes, key=lambda item: item.node_id),
        edges=sorted(edges, key=lambda item: item.edge_id),
    )


def _node_from_entity_link(link: EntityLinkState) -> MemoryGraphNode:
    return MemoryGraphNode(
        node_id=entity_node_id(link.link_id),
        node_type=MemoryGraphNodeType.ENTITY,
        label=link.canonical_entity_id,
        canonical_id=link.canonical_entity_id,
        lifecycle_state=RecordLifecycleState(link.lifecycle_state.value),
        confidence=link.confidence,
        source_record_ids=[span.source_id for span in link.evidence_spans],
        payload_ref=f"mem:evolution:entity-link:{link.link_id}",
        properties={
            "canonical_entity_id": link.canonical_entity_id,
            "normalized_name": link.normalized_name,
            "entity_type": link.entity_type.value,
            "aliases": "|".join(link.aliases),
            "superseded_by_entity_id": link.superseded_by_entity_id or "",
        },
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


def _node_from_claim_state(state: ClaimState) -> MemoryGraphNode:
    return MemoryGraphNode(
        node_id=claim_node_id(state.claim_id),
        node_type=MemoryGraphNodeType.CLAIM,
        label=f"{state.claim_key.subject_entity_id} {state.claim_key.predicate_id} {state.object_value}",
        canonical_id=state.claim_id,
        lifecycle_state=RecordLifecycleState(state.lifecycle_state.value),
        confidence=state.confidence.calibrated,
        source_record_ids=[span.source_id for span in state.evidence_spans],
        payload_ref=f"mem:evolution:claim:{state.claim_id}",
        properties={
            "claim_id": state.claim_id,
            "predicate_id": state.claim_key.predicate_id,
            "subject_entity_id": state.claim_key.subject_entity_id,
            "object_entity_id": state.object_link_id or "",
            "object_link_id": state.object_link_id or "",
            "object_value": state.object_value,
            "scope_key": state.claim_key.scope_key,
            "scope_user_id": state.claim_key.scope.user_id or "",
            "scope_session_id": state.claim_key.scope.session_id or "",
            "scope_task_id": state.claim_key.scope.task_id or "",
            "scope_id": state.claim_key.scope.stable_id(),
            "qualifier_key": state.claim_key.qualifier_key,
            "valid_from": state.valid_from.isoformat() if state.valid_from else "",
            "valid_to": state.valid_to.isoformat() if state.valid_to else "",
            "superseded_by_claim_id": state.superseded_by_claim_id or "",
        },
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _entity_node_for_claim_subject(
    state: ClaimState,
    link_by_id: dict[str, EntityLinkState],
) -> MemoryGraphNode:
    if state.subject_link_id and state.subject_link_id in link_by_id:
        return _node_from_entity_link(link_by_id[state.subject_link_id])
    return _candidate_entity_node(state.claim_key.subject_entity_id)


def _candidate_entity_node(entity_id: str) -> MemoryGraphNode:
    return MemoryGraphNode(
        node_id=candidate_entity_node_id(entity_id),
        node_type=MemoryGraphNodeType.ENTITY,
        label=entity_id,
        canonical_id=entity_id,
        lifecycle_state=RecordLifecycleState.CANDIDATE,
        confidence=0.4,
        payload_ref=f"candidate:{entity_id}",
        properties={
            "canonical_entity_id": entity_id,
            "normalized_name": normalize_value(entity_id),
            "entity_type": "unknown",
            "aliases": entity_id,
            "superseded_by_entity_id": "",
        },
    )


def _literal_node(
    value: str,
    *,
    lifecycle_state: RecordLifecycleState | ClaimLifecycleState | EntityLinkLifecycleState = (
        RecordLifecycleState.ACTIVE
    ),
    confidence: float = 0.8,
) -> MemoryGraphNode:
    return MemoryGraphNode(
        node_id=literal_node_id(value),
        node_type=MemoryGraphNodeType.LITERAL,
        label=value,
        canonical_id=normalize_value(value),
        lifecycle_state=_graph_lifecycle_state(lifecycle_state),
        confidence=confidence,
        payload_ref=f"literal:{normalize_value(value)}",
        properties={"value": value, "normalized_value": normalize_value(value)},
    )


def _scope_node(scope: MemoryScope) -> MemoryGraphNode:
    scope_key = scope.scope_key
    scope_type = "task" if scope_key.startswith("task:") else "global" if scope_key == "global" else "custom"
    return MemoryGraphNode(
        node_id=scope_node_id(scope),
        node_type=MemoryGraphNodeType.SCOPE,
        label=scope_key,
        canonical_id=scope.stable_id(),
        lifecycle_state=RecordLifecycleState.ACTIVE,
        confidence=1.0,
        payload_ref=f"scope:{scope_key}",
        properties={
            "scope_key": scope_key,
            "scope_type": scope_type,
            "user_id": scope.user_id or "",
            "session_id": scope.session_id or "",
            "task_id": scope.task_id or "",
        },
    )


def _task_node(task_id: str) -> MemoryGraphNode:
    return MemoryGraphNode(
        node_id=task_node_id(task_id),
        node_type=MemoryGraphNodeType.TASK,
        label=task_id,
        canonical_id=task_id,
        lifecycle_state=RecordLifecycleState.ACTIVE,
        confidence=0.7,
        payload_ref=f"task:{task_id}",
        properties={"task_id": task_id},
    )


def _source_node_from_span(
    span: EvidenceSpan,
    source_by_id: dict[str, SourceObservation],
) -> MemoryGraphNode:
    observation = source_by_id.get(span.source_id)
    if observation is not None:
        return MemoryGraphProjector()._add_source_observation({}, observation)
    return MemoryGraphNode(
        node_id=source_node_id(span.source_id),
        node_type=MemoryGraphNodeType.SOURCE_OBSERVATION,
        label=span.quote[:80],
        canonical_id=span.source_id,
        lifecycle_state=RecordLifecycleState.ACTIVE,
        confidence=1.0,
        source_record_ids=[span.source_id],
        payload_ref=span.source_id,
        properties={
            "source_type": span.source_type.value,
            "modality": "",
            "trigger_mode": "",
            "domain": "",
            "session_id": "",
            "task_id": "",
            "user_id": "",
        },
        created_at=span.timestamp,
        updated_at=span.timestamp,
    )


def _span_id(span: EvidenceSpan) -> str:
    return stable_graph_id("graph:span", f"{span.source_id}|{span.quote}|{span.char_start}|{span.char_end}")


def _graph_lifecycle_state(
    lifecycle_state: RecordLifecycleState | ClaimLifecycleState | EntityLinkLifecycleState,
) -> RecordLifecycleState:
    if isinstance(lifecycle_state, RecordLifecycleState):
        return lifecycle_state
    return RecordLifecycleState(lifecycle_state.value)
