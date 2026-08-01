"""Runtime graph item normalization helpers."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from memorii.core.benchmark.memory_evolution_runtime.models import (
    GraphItemNormalizationResult,
    RuntimeActionGraphItemRow,
    RuntimeClaimGraphItemRow,
    RuntimeEntityGraphItemRow,
    RuntimeGraphItem,
    RuntimeRelationGraphItemRow,
    RuntimeRelationType,
)
from memorii.core.benchmark.memory_evolution_runtime.utils import ordered_unique
from memorii.core.benchmark.memory_evolution_sim import LatentClaim, LatentEntity, SurfaceObservation
from memorii.core.memory_evolution import (
    EntityType,
    EvidenceSpan,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    SourceObservation,
    WorkStateStatus,
    normalize_work_state_status,
)
from memorii.domain.enums import SourceType


def graph_items_from_snapshot(
    *,
    scenario_id: str,
    snapshot: MemoryGraphSnapshot,
    source_id_to_event_id: dict[str, str],
) -> GraphItemNormalizationResult:
    node_by_id = {node.node_id: node for node in snapshot.nodes}
    subject_by_claim: dict[str, str] = {}
    object_by_claim: dict[str, str] = {}
    literal_object_by_claim: dict[str, str] = {}
    scope_by_claim: dict[str, str] = {}
    evidence_by_claim: dict[str, list[str]] = {}
    relation_rows: list[RuntimeGraphItem] = []
    validation_errors: list[str] = []
    for edge in snapshot.edges:
        if edge.edge_type == MemoryGraphEdgeType.HAS_SUBJECT:
            subject_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.HAS_OBJECT:
            object_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.HAS_LITERAL_OBJECT:
            literal_object_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.HAS_SCOPE:
            scope_by_claim[edge.source_node_id] = edge.target_node_id
        elif edge.edge_type == MemoryGraphEdgeType.OBSERVED_IN:
            source_node = node_by_id.get(edge.target_node_id)
            for source_id in source_node.source_record_ids if source_node else []:
                evidence_by_claim.setdefault(edge.source_node_id, []).append(
                    source_id_to_event_id.get(source_id, source_id)
                )
        if edge.edge_type in {
            MemoryGraphEdgeType.CONFLICTS_WITH,
            MemoryGraphEdgeType.CONTRADICTS,
            MemoryGraphEdgeType.SUPERSEDES,
            MemoryGraphEdgeType.MERGED_INTO,
            MemoryGraphEdgeType.SPLIT_FROM,
            MemoryGraphEdgeType.REKEYED_FROM,
        }:
            _capture_graph_item(
                rows=relation_rows,
                validation_errors=validation_errors,
                runtime_item_id=edge.edge_id,
                create=lambda edge=edge: RuntimeRelationGraphItemRow(
                    scenario_id=scenario_id,
                    runtime_item_id=edge.edge_id,
                    relation_type=_runtime_edge_relation_type(edge.edge_type),
                    source=_canonical_payload(node_by_id.get(edge.source_node_id)),
                    target=_canonical_payload(node_by_id.get(edge.target_node_id)),
                    directionality="directed" if edge.directed else "undirected",
                    lifecycle_state=edge.lifecycle_state,
                    confidence=edge.confidence,
                    evidence_event_ids=sorted(
                        {source_id_to_event_id.get(source_id, source_id) for source_id in edge.source_record_ids}
                    ),
                ),
            )
    rows: list[RuntimeGraphItem] = []
    for node in snapshot.nodes:
        if node.node_type == MemoryGraphNodeType.ENTITY:
            _capture_graph_item(
                rows=rows,
                validation_errors=validation_errors,
                runtime_item_id=node.node_id,
                create=lambda node=node: RuntimeEntityGraphItemRow(
                    scenario_id=scenario_id,
                    runtime_item_id=node.node_id,
                    canonical_name=node.properties.get("normalized_name") or node.label,
                    canonical_id=node.canonical_id or "",
                    entity_type=node.properties.get("entity_type", "unknown"),
                    aliases=[alias for alias in node.properties.get("aliases", "").split("|") if alias],
                    lifecycle_state=node.lifecycle_state,
                    confidence=node.confidence,
                    evidence_event_ids=sorted(
                        {source_id_to_event_id.get(source_id, source_id) for source_id in node.source_record_ids}
                    ),
                ),
            )
        elif node.node_type == MemoryGraphNodeType.CLAIM:
            subject_node = node_by_id.get(subject_by_claim.get(node.node_id, ""))
            object_node = node_by_id.get(object_by_claim.get(node.node_id, ""))
            literal_node = node_by_id.get(literal_object_by_claim.get(node.node_id, ""))
            scope_node = node_by_id.get(scope_by_claim.get(node.node_id, ""))
            _capture_graph_item(
                rows=rows,
                validation_errors=validation_errors,
                runtime_item_id=node.node_id,
                create=lambda node=node, subject_node=subject_node, object_node=object_node, literal_node=literal_node, scope_node=scope_node: (
                    RuntimeClaimGraphItemRow(
                        scenario_id=scenario_id,
                        runtime_item_id=node.node_id,
                        claim_id=node.properties.get("claim_id") or node.canonical_id or "",
                        subject=_entity_name(subject_node) or node.properties.get("subject_entity_id", ""),
                        subject_entity_id=(
                            node.properties.get("subject_entity_id", "")
                            or (subject_node.canonical_id if subject_node else "")
                            or ""
                        ),
                        predicate=node.properties.get("predicate_id", ""),
                        object=_entity_name(object_node)
                        or _literal_value(literal_node)
                        or node.properties.get("object_value", ""),
                        object_entity_id=object_node.canonical_id or "" if object_node else "",
                        object_value=node.properties.get("object_value", ""),
                        scope=node.properties.get("scope_key")
                        or (scope_node.properties.get("scope_key", "") if scope_node else ""),
                        valid_from=node.properties.get("valid_from", ""),
                        valid_to=node.properties.get("valid_to", ""),
                        lifecycle_state=node.lifecycle_state,
                        confidence=node.confidence,
                        evidence_event_ids=ordered_unique(evidence_by_claim.get(node.node_id, [])),
                    )
                ),
            )
        elif node.node_type == MemoryGraphNodeType.ACTION:
            _capture_graph_item(
                rows=rows,
                validation_errors=validation_errors,
                runtime_item_id=node.node_id,
                create=lambda node=node: RuntimeActionGraphItemRow(
                    scenario_id=scenario_id,
                    runtime_item_id=node.node_id,
                    action_id=node.properties.get("action_id", ""),
                    action_type=node.properties.get("action_type", ""),
                    status=_execution_status(node),
                    target_entity_ids=[
                        item for item in node.properties.get("target_entity_ids", "").split("|") if item
                    ],
                    lifecycle_state=node.lifecycle_state,
                    confidence=node.confidence,
                    evidence_event_ids=sorted(
                        {source_id_to_event_id.get(source_id, source_id) for source_id in node.source_record_ids}
                    ),
                ),
            )
    return GraphItemNormalizationResult(
        items=rows + relation_rows,
        validation_errors=validation_errors,
    )


def _capture_graph_item(
    *,
    rows: list[RuntimeGraphItem],
    validation_errors: list[str],
    runtime_item_id: str,
    create: Callable[[], RuntimeGraphItem],
) -> None:
    try:
        rows.append(create())
    except ValidationError as exc:
        fields = sorted(".".join(str(part) for part in error["loc"]) for error in exc.errors(include_url=False))
        validation_errors.append(f"malformed_graph_row:{runtime_item_id}:invalid_{'_and_'.join(fields) or 'payload'}")


def _execution_status(node: MemoryGraphNode) -> WorkStateStatus:
    persisted = node.properties.get("execution_status", "")
    normalized = normalize_work_state_status(persisted or node.properties.get("status", ""))
    return normalized


def _runtime_edge_relation_type(edge_type: MemoryGraphEdgeType) -> RuntimeRelationType:
    mapping = {
        MemoryGraphEdgeType.CONTRADICTS: "contradicts",
        MemoryGraphEdgeType.CONFLICTS_WITH: "contradicts",
        MemoryGraphEdgeType.SUPERSEDES: "supersedes",
        MemoryGraphEdgeType.MERGED_INTO: "merged_into",
        MemoryGraphEdgeType.SPLIT_FROM: "split_from",
        MemoryGraphEdgeType.REKEYED_FROM: "rekeyed_from",
    }
    return RuntimeRelationType(mapping.get(edge_type, edge_type.value))


def _canonical_payload(node: MemoryGraphNode | None) -> str:
    if node is None:
        return ""
    return str(
        node.canonical_id
        or node.properties.get("claim_id")
        or node.properties.get("canonical_entity_id")
        or node.node_id
    )


def _entity_name(node: MemoryGraphNode | None) -> str:
    if node is None:
        return ""
    return str(node.properties.get("normalized_name") or node.label)


def _literal_value(node: MemoryGraphNode | None) -> str:
    if node is None:
        return ""
    return str(node.properties.get("value") or node.properties.get("normalized_value") or node.label)


def title_from_normalized(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def runtime_entity_type(value: str) -> EntityType:
    mapping = {
        "project": EntityType.PROJECT,
        "person": EntityType.PERSON,
        "service": EntityType.SERVICE,
        "task": EntityType.TASK,
        "preference": EntityType.PREFERENCE,
    }
    return mapping.get(value, EntityType.UNKNOWN)


def _source_type_for_surface(observation: SurfaceObservation) -> SourceType:
    if observation.source_type == "tool":
        return SourceType.TOOL
    if observation.source_type == "assistant":
        return SourceType.AGENT
    if observation.source_type in {"verified_observation", "user"}:
        return SourceType.USER
    return SourceType.DERIVED


def runtime_span_for_item(
    *, surface: SurfaceObservation, runtime_observation: SourceObservation, quote: str, cache: dict[str, EvidenceSpan]
) -> EvidenceSpan:
    quote = quote if quote and quote in runtime_observation.text else runtime_observation.text
    cached = cache.get(quote)
    if cached is not None:
        return cached
    start = runtime_observation.text.find(quote)
    span = EvidenceSpan(
        source_id=runtime_observation.source_id,
        quote=quote,
        char_start=start if start >= 0 else None,
        char_end=(start + len(quote)) if start >= 0 else None,
        source_type=_source_type_for_surface(surface),
        timestamp=runtime_observation.timestamp,
    )
    cache[quote] = span
    return span


def claim_quote(claim: LatentClaim, surface: SurfaceObservation) -> str:
    for span in claim.evidence.spans:
        if span.event_id == surface.event_id and span.quote in surface.text:
            return span.quote
    return claim.evidence.spans[0].quote if claim.evidence.spans else surface.text


def entity_quote(entity: LatentEntity, surface: SurfaceObservation) -> str:
    surface_name = entity_mention_text(entity, surface.text)
    if surface_name in surface.text:
        return surface_name
    for span in entity.evidence_spans:
        if span.event_id == surface.event_id and span.quote in surface.text:
            return span.quote
    return entity.canonical_name if entity.canonical_name in surface.text else surface.text


def entity_mention_text(entity: LatentEntity, quote: str) -> str:
    """Return the longest declared entity surface that occurs in the quote."""

    candidates = (entity.canonical_name, *(alias.alias_text for alias in entity.aliases))
    matches = [candidate for candidate in candidates if candidate and candidate in quote]
    return max(matches, key=len) if matches else entity.canonical_name
