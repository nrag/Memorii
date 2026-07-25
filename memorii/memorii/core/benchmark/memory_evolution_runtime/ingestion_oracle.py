"""Independent semantic verification of persisted ingestion prefixes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.benchmark.memory_evolution_sim.schemas import (
    LatentClaim,
    LatentEntity,
    LatentGraphScenario,
    LatentRelation,
    ObservabilityLabel,
    SurfaceObservation,
)
from memorii.core.memory_evolution.models import (
    MemoryGraphEdge,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    RecordLifecycleState,
)


class IngestionPrefixIssue(BaseModel):
    """One semantic mismatch found without using production comparison logic."""

    code: str = Field(min_length=1)
    semantic_kind: str = Field(min_length=1)
    expected: str
    actual: str

    model_config = ConfigDict(extra="forbid", frozen=True)


class IngestionPrefixAuditRow(BaseModel):
    """Semantic status of the persisted graph after one source observation."""

    scenario_id: str = Field(min_length=1)
    observation_index: int = Field(ge=0)
    event_id: str = Field(min_length=1)
    timestamp: datetime
    passed: bool
    first_divergent_stage: str | None = None
    issues: list[IngestionPrefixIssue] = Field(default_factory=list)
    expected_entity_count: int = Field(ge=0)
    expected_claim_count: int = Field(ge=0)
    expected_action_count: int = Field(ge=0)
    expected_relation_count: int = Field(ge=0)
    observed_entity_count: int = Field(ge=0)
    observed_claim_count: int = Field(ge=0)
    observed_action_count: int = Field(ge=0)

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_verdict(self) -> IngestionPrefixAuditRow:
        if self.passed == bool(self.issues):
            raise ValueError("passed must be true exactly when issues is empty")
        if self.passed != (self.first_divergent_stage is None):
            raise ValueError(
                "first_divergent_stage must be absent on pass and present on failure"
            )
        return self


@dataclass(frozen=True)
class _ExpectedPrefix:
    entities: tuple[LatentEntity, ...]
    claims: tuple[LatentClaim, ...]
    relations: tuple[LatentRelation, ...]
    visible_event_ids: frozenset[str]
    visible_claim_ids: frozenset[str]
    rejected_claim_events: frozenset[tuple[str, str]]
    timestamp: datetime


@dataclass(frozen=True)
class _ObservedIndex:
    nodes: dict[str, MemoryGraphNode]
    outgoing: dict[str, tuple[MemoryGraphEdge, ...]]
    entities: tuple[MemoryGraphNode, ...]
    claims: tuple[MemoryGraphNode, ...]
    actions: tuple[MemoryGraphNode, ...]


_RELATION_EDGE_TYPES = {
    "alias_of": MemoryGraphEdgeType.ALIAS_OF,
    "contradicts": MemoryGraphEdgeType.CONFLICTS_WITH,
    "supersedes": MemoryGraphEdgeType.SUPERSEDES,
    "merged_into": MemoryGraphEdgeType.MERGED_INTO,
    "split_from": MemoryGraphEdgeType.SPLIT_FROM,
    "rekeyed_from": MemoryGraphEdgeType.REKEYED_FROM,
    "depends_on": MemoryGraphEdgeType.DEPENDS_ON,
    "blocks": MemoryGraphEdgeType.BLOCKS,
    "observed_in": MemoryGraphEdgeType.OBSERVED_IN,
}


def audit_ingestion_prefix(
    *,
    scenario: LatentGraphScenario,
    observations: Sequence[SurfaceObservation],
    snapshot: MemoryGraphSnapshot,
    source_id_to_event_id: dict[str, str],
) -> IngestionPrefixAuditRow:
    """Compare one persisted prefix to independently reconstructed expectations."""

    if not observations:
        raise ValueError("ingestion prefix requires at least one observation")
    prefix = _expected_prefix(scenario=scenario, observations=observations)
    observed = _observed_index(snapshot)
    issues: list[IngestionPrefixIssue] = []
    entity_nodes = _compare_entities(
        prefix=prefix,
        observed=observed,
        source_id_to_event_id=source_id_to_event_id,
        issues=issues,
    )
    claim_nodes = _compare_claims(
        prefix=prefix,
        observed=observed,
        entity_nodes=entity_nodes,
        source_id_to_event_id=source_id_to_event_id,
        issues=issues,
    )
    action_nodes = _compare_actions(
        prefix=prefix,
        observed=observed,
        entity_nodes=entity_nodes,
        source_id_to_event_id=source_id_to_event_id,
        issues=issues,
    )
    relation_edges = _compare_relations(
        prefix=prefix,
        observed=observed,
        entity_nodes=entity_nodes,
        claim_nodes=claim_nodes,
        source_id_to_event_id=source_id_to_event_id,
        issues=issues,
    )
    _compare_unexpected_observed_items(
        prefix=prefix,
        observed=observed,
        entity_nodes=entity_nodes,
        claim_nodes=claim_nodes,
        action_nodes=action_nodes,
        relation_edges=relation_edges,
        source_id_to_event_id=source_id_to_event_id,
        issues=issues,
    )
    issues = sorted(
        {issue.model_dump_json(): issue for issue in issues}.values(),
        key=lambda issue: (issue.code, issue.semantic_kind, issue.expected, issue.actual),
    )
    final_observation = observations[-1]
    expected_actions = [claim for claim in prefix.claims if claim.claim_kind == "action_state"]
    return IngestionPrefixAuditRow(
        scenario_id=scenario.scenario_id,
        observation_index=len(observations) - 1,
        event_id=final_observation.event_id,
        timestamp=final_observation.timestamp,
        passed=not issues,
        first_divergent_stage=None if not issues else _first_divergent_stage(issues),
        issues=issues,
        expected_entity_count=sum(
            len(_expected_entity_scopes(prefix, entity))
            for entity in prefix.entities
        ),
        expected_claim_count=len(prefix.claims),
        expected_action_count=len(expected_actions),
        expected_relation_count=len(prefix.relations),
        observed_entity_count=len(observed.entities),
        observed_claim_count=len(observed.claims),
        observed_action_count=len(observed.actions),
    )


def _expected_prefix(
    *,
    scenario: LatentGraphScenario,
    observations: Sequence[SurfaceObservation],
) -> _ExpectedPrefix:
    visible_entity_ids = {
        entity_id for observation in observations for entity_id in observation.exposed_entity_ids
    }
    visible_claim_ids = {
        claim_id for observation in observations for claim_id in observation.exposed_claim_ids
    }
    visible_relation_ids = {
        relation_id for observation in observations for relation_id in observation.exposed_relation_ids
    }
    visible_event_ids = frozenset(observation.event_id for observation in observations)
    claim_by_id = {claim.claim_id: claim for claim in scenario.claims}
    rejected_claim_events = frozenset(
        (claim_id, observation.event_id)
        for observation in observations
        for claim_id in observation.exposed_claim_ids
        if (
            (claim := claim_by_id.get(claim_id)) is not None
            and observation.event_id not in claim.evidence.source_event_ids
        )
    )
    entities = tuple(
        entity
        for entity in scenario.entities
        if entity.entity_id in visible_entity_ids
        and entity.observability != ObservabilityLabel.HIDDEN
    )
    claims = tuple(
        claim
        for claim in scenario.claims
        if claim.claim_id in visible_claim_ids
        and claim.observability != ObservabilityLabel.HIDDEN
    )
    relations = tuple(
        relation
        for relation in scenario.relations
        if relation.relation_id in visible_relation_ids
        and relation.observability != ObservabilityLabel.HIDDEN
        and relation.relation_type in _RELATION_EDGE_TYPES
    )
    return _ExpectedPrefix(
        entities=entities,
        claims=claims,
        relations=relations,
        visible_event_ids=visible_event_ids,
        visible_claim_ids=frozenset(visible_claim_ids),
        rejected_claim_events=rejected_claim_events,
        timestamp=observations[-1].timestamp,
    )


def _observed_index(snapshot: MemoryGraphSnapshot) -> _ObservedIndex:
    nodes = {node.node_id: node for node in snapshot.nodes}
    outgoing_lists: dict[str, list[MemoryGraphEdge]] = {}
    for edge in snapshot.edges:
        outgoing_lists.setdefault(edge.source_node_id, []).append(edge)
    outgoing = {
        node_id: tuple(sorted(edges, key=lambda edge: edge.edge_id))
        for node_id, edges in outgoing_lists.items()
    }
    return _ObservedIndex(
        nodes=nodes,
        outgoing=outgoing,
        entities=tuple(
            node
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.ENTITY
            and node.lifecycle_state != RecordLifecycleState.CANDIDATE
        ),
        claims=tuple(
            node
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CLAIM
            and node.lifecycle_state != RecordLifecycleState.CANDIDATE
        ),
        actions=tuple(
            node
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.ACTION
            and node.lifecycle_state != RecordLifecycleState.CANDIDATE
        ),
    )


def _compare_entities(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    source_id_to_event_id: dict[str, str],
    issues: list[IngestionPrefixIssue],
) -> dict[tuple[str, str], str]:
    matched: dict[tuple[str, str], str] = {}
    reverse: dict[str, list[tuple[str, str]]] = {}
    for entity in prefix.entities:
        for scope_key in sorted(_expected_entity_scopes(prefix, entity)):
            expected_aliases = _expected_aliases(entity, prefix.timestamp)
            candidates = [
                node
                for node in observed.entities
                if expected_aliases & _observed_aliases(node)
                and node.properties.get("scope_key", "global") == scope_key
            ]
            type_candidates = [
                node
                for node in candidates
                if node.properties.get("entity_type", "") == entity.entity_type
            ]
            selected_candidates = type_candidates or candidates
            if not selected_candidates:
                _issue(
                    issues,
                    "ingestion_missing_expected_entity",
                    "entity",
                    f"{_entity_label(entity)}:{scope_key}",
                    "",
                )
                continue
            if len(selected_candidates) > 1:
                _issue(
                    issues,
                    "ingestion_unexpected_entity_split",
                    "entity",
                    f"{_entity_label(entity)}:{scope_key}",
                    ",".join(sorted(node.node_id for node in selected_candidates)),
                )
                continue
            node = selected_candidates[0]
            identity = (entity.entity_id, scope_key)
            matched[identity] = node.node_id
            reverse.setdefault(node.node_id, []).append(identity)
            actual_type = node.properties.get("entity_type", "")
            if actual_type != entity.entity_type:
                _issue(
                    issues,
                    "ingestion_entity_type_mismatch",
                    "entity",
                    f"{_entity_label(entity)}:{entity.entity_type}:{scope_key}",
                    f"{node.node_id}:{actual_type}",
                )
            expected_provenance = _entity_provenance(entity) & prefix.visible_event_ids
            actual_provenance = {
                event_id
                for source_id in node.source_record_ids
                if (
                    event_id := _source_event_id(
                        source_id,
                        source_id_to_event_id,
                    )
                )
                is not None
            }
            if expected_provenance and not actual_provenance:
                _issue(
                    issues,
                    "ingestion_entity_provenance_missing",
                    "provenance",
                    ",".join(sorted(expected_provenance)),
                    "",
                )
    for node_id, expected_ids in reverse.items():
        if len(expected_ids) > 1:
            _issue(
                issues,
                "ingestion_unexpected_entity_merge",
                "entity",
                ",".join(
                    sorted(f"{entity_id}:{scope_key}" for entity_id, scope_key in expected_ids)
                ),
                node_id,
            )
    return matched


def _compare_claims(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    entity_nodes: dict[tuple[str, str], str],
    source_id_to_event_id: dict[str, str],
    issues: list[IngestionPrefixIssue],
) -> dict[str, str]:
    matched: dict[str, str] = {}
    for claim in prefix.claims:
        subject_node_id = entity_nodes.get(
            (claim.subject.entity_id, claim.scope.scope_key)
        )
        if subject_node_id is None:
            continue
        object_node_id = (
            entity_nodes.get((claim.object.entity_id, claim.scope.scope_key))
            if claim.object.entity_id is not None
            else None
        )
        candidates = [
            node
            for node in observed.claims
            if _claim_subject(observed, node) == subject_node_id
        ]
        predicate_candidates = [
            node
            for node in candidates
            if node.properties.get("predicate_id", "") == claim.predicate.predicate_id
        ]
        if not predicate_candidates:
            actual_predicates = sorted(
                {node.properties.get("predicate_id", "") for node in candidates}
            )
            _issue(
                issues,
                (
                    "ingestion_claim_predicate_mismatch"
                    if candidates
                    else "ingestion_missing_expected_claim"
                ),
                "claim",
                _claim_label(claim),
                ",".join(actual_predicates),
            )
            continue
        object_candidates = [
            node
            for node in predicate_candidates
            if _claim_object_matches(
                observed=observed,
                node=node,
                object_node_id=object_node_id,
                object_value=claim.object.normalized_value or claim.object.value,
            )
        ]
        if not object_candidates:
            _issue(
                issues,
                "ingestion_claim_object_mismatch",
                "claim",
                _claim_label(claim),
                ",".join(sorted(node.node_id for node in predicate_candidates)),
            )
            continue
        scope_candidates = [
            node
            for node in object_candidates
            if node.properties.get("scope_key", "") == claim.scope.scope_key
        ]
        if not scope_candidates:
            _issue(
                issues,
                "ingestion_claim_scope_mismatch",
                "claim",
                f"{_claim_label(claim)}:{claim.scope.scope_key}",
                ",".join(
                    sorted(node.properties.get("scope_key", "") for node in object_candidates)
                ),
            )
            continue
        expected_lifecycle = _claim_lifecycle_at(claim, prefix)
        expected_events = set(claim.evidence.source_event_ids) & prefix.visible_event_ids
        exact_candidates = [
            node
            for node in scope_candidates
            if node.lifecycle_state.value == expected_lifecycle
            and _node_provenance_events(
                observed=observed,
                node=node,
                source_id_to_event_id=source_id_to_event_id,
            )
            == expected_events
        ]
        selected_candidates = exact_candidates or scope_candidates
        if len(selected_candidates) != 1:
            _issue(
                issues,
                "ingestion_ambiguous_observed_claim",
                "claim",
                _claim_label(claim),
                ",".join(sorted(node.node_id for node in selected_candidates)),
            )
            continue
        node = selected_candidates[0]
        matched[claim.claim_id] = node.node_id
        if node.lifecycle_state.value != expected_lifecycle:
            _issue(
                issues,
                "ingestion_claim_lifecycle_mismatch",
                "claim",
                f"{claim.claim_id}:{expected_lifecycle}",
                f"{node.node_id}:{node.lifecycle_state.value}",
            )
        actual_events = _node_provenance_events(
            observed=observed,
            node=node,
            source_id_to_event_id=source_id_to_event_id,
        )
        if expected_events != actual_events:
            _issue(
                issues,
                "ingestion_claim_provenance_mismatch",
                "provenance",
                ",".join(sorted(expected_events)),
                ",".join(sorted(actual_events)),
            )
        expected_from, expected_to = _expected_validity(claim, prefix)
        actual_from = node.properties.get("valid_from", "")
        actual_to = node.properties.get("valid_to", "")
        if expected_from != actual_from or expected_to != actual_to:
            _issue(
                issues,
                "ingestion_claim_validity_mismatch",
                "claim",
                f"{expected_from}|{expected_to}",
                f"{actual_from}|{actual_to}",
            )
    return matched


def _compare_actions(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    entity_nodes: dict[tuple[str, str], str],
    source_id_to_event_id: dict[str, str],
    issues: list[IngestionPrefixIssue],
) -> set[str]:
    matched: set[str] = set()
    expected_actions = [claim for claim in prefix.claims if claim.claim_kind == "action_state"]
    for claim in expected_actions:
        target_node_id = entity_nodes.get(
            (claim.subject.entity_id, claim.scope.scope_key)
        )
        if target_node_id is None:
            continue
        expected_status = _normalize(claim.object.normalized_value or claim.object.value)
        candidates = [
            node
            for node in observed.actions
            if target_node_id in _edge_targets(
                observed,
                node,
                MemoryGraphEdgeType.HAS_OBJECT,
            )
        ]
        matching = [
            node
            for node in candidates
            if _normalize(
                node.properties.get("execution_status")
                or node.properties.get("status", "")
            )
            == expected_status
        ]
        if len(matching) != 1:
            _issue(
                issues,
                (
                    "ingestion_action_status_mismatch"
                    if candidates
                    else "ingestion_missing_expected_action"
                ),
                "action",
                f"{claim.subject.canonical_name}:{expected_status}",
                ",".join(
                    sorted(node.properties.get("status", "") for node in candidates)
                ),
            )
            continue
        matched.add(matching[0].node_id)
        expected_events = set(claim.evidence.source_event_ids) & prefix.visible_event_ids
        actual_events = _node_provenance_events(
            observed=observed,
            node=matching[0],
            source_id_to_event_id=source_id_to_event_id,
        )
        if expected_events != actual_events:
            _issue(
                issues,
                "ingestion_action_provenance_mismatch",
                "provenance",
                ",".join(sorted(expected_events)),
                ",".join(sorted(actual_events)),
            )
    return matched


def _compare_relations(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    entity_nodes: dict[tuple[str, str], str],
    claim_nodes: dict[str, str],
    source_id_to_event_id: dict[str, str],
    issues: list[IngestionPrefixIssue],
) -> set[str]:
    matched: set[str] = set()
    all_edges = tuple(edge for edges in observed.outgoing.values() for edge in edges)
    for relation in prefix.relations:
        edge_type = _RELATION_EDGE_TYPES[relation.relation_type]
        alias_label: str | None = None
        if (
            relation.relation_type == "alias_of"
            and relation.source.endpoint_type == "alias"
            and relation.target.endpoint_type == "entity"
        ):
            source_id = _relation_endpoint_node(
                relation.target.endpoint_type,
                relation.target.endpoint_id,
                entity_nodes=entity_nodes,
                claim_nodes=claim_nodes,
            )
            alias_label = relation.source.label
        else:
            source_id = _relation_endpoint_node(
                relation.source.endpoint_type,
                relation.source.endpoint_id,
                entity_nodes=entity_nodes,
                claim_nodes=claim_nodes,
            )
        if source_id is None:
            continue
        candidates = [
            edge
            for edge in all_edges
            if edge.edge_type == edge_type and edge.source_node_id == source_id
        ]
        if alias_label is not None:
            candidates = [
                edge
                for edge in candidates
                if _normalize(observed.nodes[edge.target_node_id].label)
                == _normalize(alias_label)
            ]
        elif relation.target.endpoint_type == "source_event":
            candidates = [
                edge
                for edge in candidates
                if (target := observed.nodes.get(edge.target_node_id)) is not None
                and target.canonical_id is not None
                and source_id_to_event_id.get(target.canonical_id)
                == relation.target.endpoint_id
            ]
        elif relation.target.endpoint_type == "alias":
            candidates = [
                edge
                for edge in candidates
                if _normalize(observed.nodes[edge.target_node_id].label)
                == _normalize(relation.target.label)
            ]
        else:
            target_id = _relation_endpoint_node(
                relation.target.endpoint_type,
                relation.target.endpoint_id,
                entity_nodes=entity_nodes,
                claim_nodes=claim_nodes,
            )
            candidates = [
                edge for edge in candidates if edge.target_node_id == target_id
            ]
        if not candidates:
            _issue(
                issues,
                "ingestion_missing_expected_relation",
                "relation",
                f"{relation.relation_type}:{relation.source.label}->{relation.target.label}",
                "",
            )
            continue
        matched.add(sorted(candidates, key=lambda edge: edge.edge_id)[0].edge_id)
    for edge_type, source_claim_id, target_claim_id in sorted(
        _expected_lifecycle_relations(prefix),
        key=lambda item: (item[0].value, item[1], item[2]),
    ):
        source_id = claim_nodes.get(source_claim_id)
        target_id = claim_nodes.get(target_claim_id)
        if source_id is None or target_id is None:
            continue
        candidates = [
            edge
            for edge in all_edges
            if edge.edge_type == edge_type
            and edge.source_node_id == source_id
            and edge.target_node_id == target_id
        ]
        if not candidates:
            _issue(
                issues,
                "ingestion_missing_expected_relation",
                "relation",
                f"{edge_type.value}:{source_claim_id}->{target_claim_id}",
                "",
            )
            continue
        matched.add(sorted(candidates, key=lambda edge: edge.edge_id)[0].edge_id)
    return matched


def _compare_unexpected_observed_items(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    entity_nodes: dict[tuple[str, str], str],
    claim_nodes: dict[str, str],
    action_nodes: set[str],
    relation_edges: set[str],
    source_id_to_event_id: dict[str, str],
    issues: list[IngestionPrefixIssue],
) -> None:
    expected_entity_nodes = set(entity_nodes.values())
    for node in observed.entities:
        if node.node_id not in expected_entity_nodes:
            _issue(
                issues,
                "ingestion_unexpected_observed_entity",
                "entity",
                "",
                node.node_id,
            )

    expected_claim_nodes = set(claim_nodes.values())
    for node in observed.claims:
        if (
            node.node_id in expected_claim_nodes
            or _is_allowed_entity_type_claim(
                prefix=prefix,
                observed=observed,
                node=node,
                entity_nodes=expected_entity_nodes,
                source_id_to_event_id=source_id_to_event_id,
            )
            or _is_expected_rejected_observation_claim(
                prefix=prefix,
                observed=observed,
                node=node,
                entity_nodes=entity_nodes,
                source_id_to_event_id=source_id_to_event_id,
            )
        ):
            continue
        _issue(
            issues,
            "ingestion_unexpected_observed_claim",
            "claim",
            "",
            node.node_id,
        )

    for node in observed.actions:
        if node.node_id not in action_nodes:
            _issue(
                issues,
                "ingestion_unexpected_observed_action",
                "action",
                "",
                node.node_id,
            )

    semantic_relation_types = set(_RELATION_EDGE_TYPES.values()) - {
        MemoryGraphEdgeType.OBSERVED_IN,
    }
    all_edges = tuple(edge for edges in observed.outgoing.values() for edge in edges)
    for edge in all_edges:
        if (
            edge.edge_type in semantic_relation_types
            and edge.edge_id not in relation_edges
            and not _is_expected_alias_edge(
                prefix=prefix,
                observed=observed,
                edge=edge,
                entity_nodes=entity_nodes,
            )
            and not _is_expected_rejected_claim_relation(
                prefix=prefix,
                observed=observed,
                edge=edge,
                entity_nodes=entity_nodes,
                claim_nodes=claim_nodes,
                source_id_to_event_id=source_id_to_event_id,
            )
        ):
            _issue(
                issues,
                "ingestion_unexpected_observed_relation",
                "relation",
                "",
                edge.edge_id,
            )


def _expected_lifecycle_relations(
    prefix: _ExpectedPrefix,
) -> set[tuple[MemoryGraphEdgeType, str, str]]:
    visible_claim_ids = {claim.claim_id for claim in prefix.claims}
    expected: set[tuple[MemoryGraphEdgeType, str, str]] = set()
    for claim in prefix.claims:
        for target_claim_id in claim.lifecycle.supersedes_claim_ids:
            if target_claim_id in visible_claim_ids:
                expected.add(
                    (
                        MemoryGraphEdgeType.SUPERSEDES,
                        claim.claim_id,
                        target_claim_id,
                    )
                )
        if (
            claim.lifecycle.superseded_by_claim_id is not None
            and claim.lifecycle.superseded_by_claim_id in visible_claim_ids
        ):
            expected.add(
                (
                    MemoryGraphEdgeType.SUPERSEDES,
                    claim.lifecycle.superseded_by_claim_id,
                    claim.claim_id,
                )
            )
        for target_claim_id in claim.lifecycle.conflict_with_claim_ids:
            if target_claim_id in visible_claim_ids:
                expected.add(
                    (
                        MemoryGraphEdgeType.CONFLICTS_WITH,
                        claim.claim_id,
                        target_claim_id,
                    )
                )
    return expected


def _is_expected_rejected_observation_claim(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    node: MemoryGraphNode,
    entity_nodes: dict[tuple[str, str], str],
    source_id_to_event_id: dict[str, str],
) -> bool:
    return (
        _expected_rejected_observation_claim_id(
            prefix=prefix,
            observed=observed,
            node=node,
            entity_nodes=entity_nodes,
            source_id_to_event_id=source_id_to_event_id,
        )
        is not None
    )


def _expected_rejected_observation_claim_id(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    node: MemoryGraphNode,
    entity_nodes: dict[tuple[str, str], str],
    source_id_to_event_id: dict[str, str],
) -> str | None:
    if node.lifecycle_state != RecordLifecycleState.INVALIDATED:
        return None
    provenance = _node_provenance_events(
        observed=observed,
        node=node,
        source_id_to_event_id=source_id_to_event_id,
    )
    if len(provenance) != 1:
        return None
    event_id = next(iter(provenance))
    for claim in prefix.claims:
        if (claim.claim_id, event_id) not in prefix.rejected_claim_events:
            continue
        subject_node_id = entity_nodes.get(
            (claim.subject.entity_id, claim.scope.scope_key)
        )
        object_node_id = (
            entity_nodes.get((claim.object.entity_id, claim.scope.scope_key))
            if claim.object.entity_id is not None
            else None
        )
        if (
            subject_node_id is not None
            and _claim_subject(observed, node) == subject_node_id
            and node.properties.get("predicate_id", "")
            == claim.predicate.predicate_id
            and node.properties.get("scope_key", "") == claim.scope.scope_key
            and _claim_object_matches(
                observed=observed,
                node=node,
                object_node_id=object_node_id,
                object_value=claim.object.normalized_value or claim.object.value,
            )
        ):
            return claim.claim_id
    return None


def _is_expected_rejected_claim_relation(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    edge: MemoryGraphEdge,
    entity_nodes: dict[tuple[str, str], str],
    claim_nodes: dict[str, str],
    source_id_to_event_id: dict[str, str],
) -> bool:
    if edge.edge_type != MemoryGraphEdgeType.CONFLICTS_WITH:
        return False
    source = observed.nodes.get(edge.source_node_id)
    if source is None:
        return False
    rejected_claim_id = _expected_rejected_observation_claim_id(
        prefix=prefix,
        observed=observed,
        node=source,
        entity_nodes=entity_nodes,
        source_id_to_event_id=source_id_to_event_id,
    )
    if rejected_claim_id is None:
        return False
    target_claim_ids = {
        claim_id
        for claim_id, node_id in claim_nodes.items()
        if node_id == edge.target_node_id
    }
    if len(target_claim_ids) != 1:
        return False
    target_claim_id = next(iter(target_claim_ids))
    rejected_claim = next(
        (
            claim
            for claim in prefix.claims
            if claim.claim_id == rejected_claim_id
        ),
        None,
    )
    return (
        rejected_claim is not None
        and target_claim_id in rejected_claim.lifecycle.conflict_with_claim_ids
    )


def _is_expected_alias_edge(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    edge: MemoryGraphEdge,
    entity_nodes: dict[tuple[str, str], str],
) -> bool:
    if edge.edge_type != MemoryGraphEdgeType.ALIAS_OF:
        return False
    target = observed.nodes.get(edge.target_node_id)
    if target is None:
        return False
    expected_entity_ids = {
        entity_id
        for (entity_id, _scope_key), node_id in entity_nodes.items()
        if node_id == edge.source_node_id
    }
    if len(expected_entity_ids) != 1:
        return False
    expected_entity_id = next(iter(expected_entity_ids))
    entity = next(
        (
            candidate
            for candidate in prefix.entities
            if candidate.entity_id == expected_entity_id
        ),
        None,
    )
    if entity is None:
        return False
    expected_aliases = {_normalize(entity.canonical_name)}
    expected_aliases.update(
        _normalize(alias.alias_text)
        for alias in entity.aliases
        if alias.valid_from <= prefix.timestamp
        and (alias.valid_to is None or prefix.timestamp < alias.valid_to)
        and any(
            span.event_id in prefix.visible_event_ids
            for span in alias.evidence_spans
        )
    )
    return _normalize(target.label) in expected_aliases


def _is_allowed_entity_type_claim(
    *,
    prefix: _ExpectedPrefix,
    observed: _ObservedIndex,
    node: MemoryGraphNode,
    entity_nodes: set[str],
    source_id_to_event_id: dict[str, str],
) -> bool:
    if node.properties.get("predicate_id") != "entity_type":
        return False
    subject_ids = _edge_targets(
        observed,
        node,
        MemoryGraphEdgeType.HAS_SUBJECT,
    )
    literal_ids = _edge_targets(
        observed,
        node,
        MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
    )
    if len(subject_ids) != 1 or len(literal_ids) != 1:
        return False
    subject_id = next(iter(subject_ids))
    literal = observed.nodes.get(next(iter(literal_ids)))
    subject = observed.nodes.get(subject_id)
    if (
        subject_id not in entity_nodes
        or subject is None
        or literal is None
        or literal.properties.get("normalized_value", "")
        != subject.properties.get("entity_type", "")
    ):
        return False
    provenance = _node_provenance_events(
        observed=observed,
        node=node,
        source_id_to_event_id=source_id_to_event_id,
    )
    return bool(provenance) and provenance.issubset(prefix.visible_event_ids)


def _expected_aliases(entity: LatentEntity, timestamp: datetime) -> set[str]:
    aliases = {_normalize(entity.canonical_name)}
    aliases.update(
        _normalize(alias.alias_text)
        for alias in entity.aliases
        if alias.valid_from <= timestamp
        and (alias.valid_to is None or timestamp < alias.valid_to)
    )
    return aliases


def _observed_aliases(node: MemoryGraphNode) -> set[str]:
    aliases = {
        _normalize(node.label),
        _normalize(node.properties.get("normalized_name", "")),
    }
    aliases.update(
        _normalize(alias)
        for alias in node.properties.get("aliases", "").split("|")
        if alias
    )
    return {alias for alias in aliases if alias}


def _entity_provenance(entity: LatentEntity) -> set[str]:
    event_ids = {span.event_id for span in entity.evidence_spans}
    for alias in entity.aliases:
        event_ids.update(span.event_id for span in alias.evidence_spans)
    return {event_id for event_id in event_ids if event_id}


def _claim_subject(observed: _ObservedIndex, node: MemoryGraphNode) -> str | None:
    targets = _edge_targets(observed, node, MemoryGraphEdgeType.HAS_SUBJECT)
    return next(iter(targets)) if len(targets) == 1 else None


def _claim_object_matches(
    *,
    observed: _ObservedIndex,
    node: MemoryGraphNode,
    object_node_id: str | None,
    object_value: str,
) -> bool:
    if object_node_id is not None:
        return object_node_id in _edge_targets(
            observed,
            node,
            MemoryGraphEdgeType.HAS_OBJECT,
        )
    literal_targets = _edge_targets(
        observed,
        node,
        MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
    )
    return any(
        _normalize(observed.nodes[target].properties.get("normalized_value", ""))
        == _normalize(object_value)
        for target in literal_targets
        if target in observed.nodes
    )


def _node_provenance_events(
    *,
    observed: _ObservedIndex,
    node: MemoryGraphNode,
    source_id_to_event_id: dict[str, str],
) -> set[str]:
    events: set[str] = set()
    for edge in observed.outgoing.get(node.node_id, ()):
        if edge.edge_type != MemoryGraphEdgeType.OBSERVED_IN:
            continue
        for source_id in edge.source_record_ids:
            event_id = _source_event_id(source_id, source_id_to_event_id)
            if event_id is not None:
                events.add(event_id)
    return events


def _source_event_id(
    source_id: str,
    source_id_to_event_id: dict[str, str],
) -> str | None:
    return source_id_to_event_id.get(source_id)


def _edge_targets(
    observed: _ObservedIndex,
    node: MemoryGraphNode,
    edge_type: MemoryGraphEdgeType,
) -> set[str]:
    return {
        edge.target_node_id
        for edge in observed.outgoing.get(node.node_id, ())
        if edge.edge_type == edge_type
    }


def _relation_endpoint_node(
    endpoint_type: str,
    endpoint_id: str,
    *,
    entity_nodes: dict[tuple[str, str], str],
    claim_nodes: dict[str, str],
) -> str | None:
    if endpoint_type == "entity":
        matches = {
            node_id
            for (entity_id, _scope_key), node_id in entity_nodes.items()
            if entity_id == endpoint_id
        }
        return next(iter(matches)) if len(matches) == 1 else None
    if endpoint_type in {"claim", "belief"}:
        return claim_nodes.get(endpoint_id)
    return None


def _claim_lifecycle_at(claim: LatentClaim, prefix: _ExpectedPrefix) -> str:
    if claim.lifecycle.state.value == "active":
        return "active"
    if (
        claim.lifecycle.valid_to is not None
        and prefix.timestamp >= claim.lifecycle.valid_to
    ):
        return claim.lifecycle.state.value
    if (
        claim.lifecycle.superseded_by_claim_id is not None
        and claim.lifecycle.superseded_by_claim_id in prefix.visible_claim_ids
    ):
        return claim.lifecycle.state.value
    if (
        claim.lifecycle.state.value == "invalidated"
        and set(claim.evidence.source_event_ids) & prefix.visible_event_ids
    ):
        return "invalidated"
    return "active"


def _expected_validity(
    claim: LatentClaim,
    prefix: _ExpectedPrefix,
) -> tuple[str, str]:
    valid_from = claim.lifecycle.valid_from
    valid_to = (
        claim.lifecycle.valid_to
        if _claim_lifecycle_at(claim, prefix) != "active"
        else None
    )
    return _time_text(valid_from), _time_text(valid_to)


def _expected_entity_scopes(
    prefix: _ExpectedPrefix,
    entity: LatentEntity,
) -> set[str]:
    scopes = {
        claim.scope.scope_key
        for claim in prefix.claims
        if claim.subject.entity_id == entity.entity_id
        or claim.object.entity_id == entity.entity_id
    }
    if not scopes:
        scopes.add("global")
    return scopes


def _first_divergent_stage(issues: Sequence[IngestionPrefixIssue]) -> str:
    priority = {
        "entity": "entity_resolution",
        "claim": "claim_compilation",
        "action": "action_compilation",
        "relation": "graph_projection",
        "provenance": "provenance_projection",
    }
    for semantic_kind in ("entity", "claim", "action", "relation", "provenance"):
        if any(issue.semantic_kind == semantic_kind for issue in issues):
            return priority[semantic_kind]
    return "semantic_graph"


def _entity_label(entity: LatentEntity) -> str:
    return f"{entity.canonical_name}:{entity.entity_type}"


def _claim_label(claim: LatentClaim) -> str:
    return (
        f"{claim.subject.canonical_name}:"
        f"{claim.predicate.predicate_id}:"
        f"{claim.object.normalized_value or claim.object.value}"
    )


def _time_text(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _normalize(value: str) -> str:
    return " ".join(value.casefold().strip(" .,:;").split())


def _issue(
    issues: list[IngestionPrefixIssue],
    code: str,
    semantic_kind: str,
    expected: str,
    actual: str,
) -> None:
    issues.append(
        IngestionPrefixIssue(
            code=code,
            semantic_kind=semantic_kind,
            expected=expected,
            actual=actual,
        )
    )
