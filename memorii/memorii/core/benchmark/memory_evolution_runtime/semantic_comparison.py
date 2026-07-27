"""Independent semantic comparison for runtime memory-evolution checkpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from memorii.core.benchmark.memory_evolution_runtime.models import (
    RuntimeActionGraphItemRow,
    RuntimeClaimGraphItemRow,
    RuntimeEntityGraphItemRow,
    RuntimeGraphItem,
    RuntimeRelationGraphItemRow,
)
from memorii.core.benchmark.memory_evolution_sim import (
    LatentClaim,
    LatentEntity,
    LatentGraphScenario,
    LatentRelation,
    OracleCheckpoint,
)
from memorii.core.memory_evolution import ProductionRetrievalDecision

SemanticChannel = Literal[
    "selected",
    "supporting",
    "context",
    "rejected",
    "uncertain",
    "graph",
    "provenance",
    "abstention",
]


def _expected_text(value: str) -> str:
    return " ".join(value.casefold().strip(" .").split())


def _observed_text(value: str) -> str:
    return " ".join(value.casefold().strip(" .").split())


def _expected_time(value: datetime | str | None) -> str:
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, datetime) else value


def _observed_time(value: datetime | str | None) -> str:
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, datetime) else value


@dataclass(frozen=True, order=True)
class CanonicalEntity:
    """ID-independent entity identity used only at the benchmark boundary."""

    canonical_name: str
    entity_type: str


@dataclass(frozen=True, order=True)
class CanonicalClaim:
    """Complete observable claim semantics, including lifecycle and provenance."""

    subject: CanonicalEntity
    predicate: str
    object_kind: Literal["entity", "literal"]
    object_value: str
    object_entity_type: str
    scope: str
    lifecycle: str
    valid_from: str
    valid_to: str
    provenance: tuple[str, ...]

    @property
    def identity(self) -> tuple[CanonicalEntity, str, str, str, str]:
        return (
            self.subject,
            self.predicate,
            self.object_kind,
            self.object_value,
            self.scope,
        )


@dataclass(frozen=True, order=True)
class CanonicalRelation:
    relation_type: str
    source: str
    target: str
    directionality: str


@dataclass(frozen=True, order=True)
class CanonicalAction:
    action_type: str
    status: str
    targets: tuple[CanonicalEntity, ...]
    provenance: tuple[str, ...]


@dataclass(frozen=True)
class SemanticComparisonIssue:
    code: str
    channel: SemanticChannel
    expected: str
    actual: str


@dataclass(frozen=True)
class SemanticComparisonResult:
    issues: tuple[SemanticComparisonIssue, ...]
    requirement_count: int

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def score(self) -> float:
        if not self.requirement_count:
            return 1.0 if self.passed else 0.0
        return max(0.0, 1.0 - len(self.issues) / self.requirement_count)

    @property
    def failure_buckets(self) -> list[str]:
        return sorted({issue.code for issue in self.issues})


@dataclass(frozen=True)
class _ExpectedView:
    selected_entities: frozenset[CanonicalEntity]
    selected_claims: frozenset[CanonicalClaim]
    supporting_claims: frozenset[CanonicalClaim]
    excluded_claims: frozenset[CanonicalClaim]
    visible_claims: frozenset[CanonicalClaim]
    visible_event_ids: frozenset[str]
    relations: frozenset[CanonicalRelation]
    actions: frozenset[CanonicalAction]
    citations: frozenset[str]
    uncertain_items: frozenset[str]
    abstention: bool


@dataclass(frozen=True)
class _ObservedView:
    selected_entities: frozenset[CanonicalEntity]
    selected_claims: frozenset[CanonicalClaim]
    supporting_claims: frozenset[CanonicalClaim]
    context_claims: frozenset[CanonicalClaim]
    rejected_claims: frozenset[CanonicalClaim]
    relations: frozenset[CanonicalRelation]
    actions: frozenset[CanonicalAction]
    citations: frozenset[str]
    uncertain_items: frozenset[str]
    unresolved_channel_ids: tuple[tuple[SemanticChannel, str], ...]
    abstention: bool


def compare_checkpoint_semantics(
    *,
    scenario: LatentGraphScenario,
    checkpoint: OracleCheckpoint,
    graph_items: list[RuntimeGraphItem],
    decision: ProductionRetrievalDecision,
    source_id_to_event_id: dict[str, str] | None = None,
) -> SemanticComparisonResult:
    """Compare independent expected and observed views without oracle-ID alignment."""

    expected = _expected_view(scenario=scenario, checkpoint=checkpoint)
    observed = _observed_view(
        graph_items=graph_items,
        decision=decision,
        source_id_to_event_id=source_id_to_event_id or {},
    )
    issues: list[SemanticComparisonIssue] = []
    _compare_exact(
        issues,
        expected.selected_claims,
        observed.selected_claims,
        missing_code="production_retrieval_missing_expected_claim",
        extra_code="production_retrieval_unexpected_selected_claim",
        channel="selected",
    )
    _compare_exact(
        issues,
        expected.selected_entities,
        observed.selected_entities,
        missing_code="production_retrieval_missing_expected_entity",
        extra_code="production_retrieval_unexpected_selected_entity",
        channel="selected",
    )
    _compare_exact(
        issues,
        expected.supporting_claims,
        observed.supporting_claims,
        missing_code="production_retrieval_missing_expected_support",
        extra_code="production_retrieval_unexpected_supporting_claim",
        channel="supporting",
    )
    _compare_required(
        issues,
        expected.excluded_claims,
        observed.rejected_claims | observed.context_claims,
        code="production_retrieval_missing_expected_rejection",
        channel="rejected",
    )
    _append_differences(
        issues,
        _unsupported_audit_claims(observed.rejected_claims, expected),
        "production_retrieval_unexpected_rejected_claim",
        "rejected",
        expected=False,
    )
    _append_differences(
        issues,
        _unsupported_audit_claims(observed.context_claims, expected),
        "production_retrieval_unexpected_context_claim",
        "context",
        expected=False,
    )
    _compare_required(
        issues,
        expected.relations,
        observed.relations,
        code="production_semantic_graph_missing_expected_relation",
        channel="graph",
    )
    _compare_exact(
        issues,
        expected.actions,
        observed.actions,
        missing_code="production_retrieval_missing_expected_action",
        extra_code="production_retrieval_unexpected_selected_action",
        channel="selected",
    )
    _compare_required(
        issues,
        expected.citations,
        observed.citations,
        code="production_semantic_graph_provenance_missing",
        channel="provenance",
    )
    _compare_exact(
        issues,
        expected.uncertain_items,
        observed.uncertain_items,
        missing_code="production_retrieval_missing_expected_uncertainty",
        extra_code="production_retrieval_unexpected_uncertainty",
        channel="uncertain",
    )
    for channel, record_id in observed.unresolved_channel_ids:
        issues.append(
            SemanticComparisonIssue(
                code="production_retrieval_unresolved_channel_record",
                channel=channel,
                expected="",
                actual=record_id,
            )
        )
    if expected.abstention != observed.abstention:
        issues.append(
            SemanticComparisonIssue(
                code=(
                    "production_retrieval_unexpected_abstention"
                    if observed.abstention
                    else "production_retrieval_missing_expected_abstention"
                ),
                channel="abstention",
                expected=str(expected.abstention),
                actual=str(observed.abstention),
            )
        )
    requirement_count = (
        len(expected.selected_claims)
        + len(expected.selected_entities)
        + len(expected.supporting_claims)
        + len(expected.excluded_claims)
        + len(expected.relations)
        + len(expected.actions)
        + len(expected.citations)
        + len(expected.uncertain_items)
        + 1
    )
    return SemanticComparisonResult(tuple(issues), requirement_count)


def _compare_exact(
    issues: list[SemanticComparisonIssue],
    expected: frozenset[object],
    observed: frozenset[object],
    *,
    missing_code: str,
    extra_code: str,
    channel: SemanticChannel,
) -> None:
    _append_differences(issues, expected - observed, missing_code, channel, expected=True)
    _append_differences(issues, observed - expected, extra_code, channel, expected=False)


def _compare_required(
    issues: list[SemanticComparisonIssue],
    expected: frozenset[object],
    observed: frozenset[object],
    *,
    code: str,
    channel: SemanticChannel,
) -> None:
    _append_differences(issues, expected - observed, code, channel, expected=True)


def _append_differences(
    issues: list[SemanticComparisonIssue],
    values: set[object] | frozenset[object],
    code: str,
    channel: SemanticChannel,
    *,
    expected: bool,
) -> None:
    for value in sorted(map(repr, values)):
        issues.append(
            SemanticComparisonIssue(
                code=code,
                channel=channel,
                expected=value if expected else "",
                actual="" if expected else value,
            )
        )


def _unsupported_audit_claims(
    claims: frozenset[CanonicalClaim],
    expected: _ExpectedView,
) -> frozenset[CanonicalClaim]:
    return frozenset(
        claim
        for claim in claims
        if claim not in expected.visible_claims
        and (not claim.provenance or not set(claim.provenance).issubset(expected.visible_event_ids))
    )


def _expected_view(*, scenario: LatentGraphScenario, checkpoint: OracleCheckpoint) -> _ExpectedView:
    entity_by_id = {entity.entity_id: entity for entity in scenario.entities}
    claim_by_id = {claim.claim_id: claim for claim in scenario.claims}
    relation_by_id = {relation.relation_id: relation for relation in scenario.relations}
    selected_claim_ids = (
        checkpoint.expected_execution_claim_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_claim_ids
    )
    selected_entity_ids = (
        checkpoint.expected_execution_entity_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_entity_ids
    )
    citation_ids = (
        checkpoint.expected_execution_citation_event_ids
        if checkpoint.checkpoint_type == "execution_continuation"
        else checkpoint.expected_citation_event_ids
    )
    selected_action_claim_ids = {action_id.removeprefix("action:") for action_id in checkpoint.expected_action_ids}
    selected_claim_ids = [claim_id for claim_id in selected_claim_ids if claim_id not in selected_action_claim_ids]
    return _ExpectedView(
        selected_entities=frozenset(_expected_entity(entity_by_id[entity_id]) for entity_id in selected_entity_ids),
        selected_claims=frozenset(
            _expected_claim(claim_by_id[claim_id], entity_by_id) for claim_id in selected_claim_ids
        ),
        supporting_claims=frozenset(
            _expected_claim(claim_by_id[claim_id], entity_by_id) for claim_id in selected_claim_ids
        ),
        excluded_claims=frozenset(
            _expected_claim(claim_by_id[claim_id], entity_by_id)
            for claim_id in checkpoint.expected_excluded_claim_ids
            if checkpoint.task_contract.excluded_ids_must_be_rejected_or_contextualized
        ),
        visible_claims=frozenset(
            _expected_claim(claim, entity_by_id) for claim in scenario.claims if claim.observability.value != "hidden"
        ),
        visible_event_ids=frozenset(observation.event_id for observation in scenario.observations),
        relations=frozenset(
            _expected_relation(relation_by_id[relation_id], entity_by_id, claim_by_id)
            for relation_id in checkpoint.expected_relation_ids
        ),
        actions=frozenset(
            _expected_action(action_id, claim_by_id, entity_by_id) for action_id in checkpoint.expected_action_ids
        ),
        citations=frozenset(citation_ids),
        uncertain_items=frozenset(
            _expected_reference(
                item_id,
                entity_by_id=entity_by_id,
                claim_by_id=claim_by_id,
                relation_by_id=relation_by_id,
            )
            for item_id in checkpoint.expected_uncertain_ids
        ),
        abstention=checkpoint.expected_abstention,
    )


def _observed_view(
    *,
    graph_items: list[RuntimeGraphItem],
    decision: ProductionRetrievalDecision,
    source_id_to_event_id: dict[str, str],
) -> _ObservedView:
    entities = [item for item in graph_items if isinstance(item, RuntimeEntityGraphItemRow)]
    claims = [item for item in graph_items if isinstance(item, RuntimeClaimGraphItemRow)]
    actions = [item for item in graph_items if isinstance(item, RuntimeActionGraphItemRow)]
    relations = [item for item in graph_items if isinstance(item, RuntimeRelationGraphItemRow)]
    entity_by_ref = {ref: item for item in entities for ref in (item.runtime_item_id, item.canonical_id)}
    claim_by_ref = {ref: item for item in claims for ref in (item.runtime_item_id, item.claim_id)}
    action_by_ref = {
        ref: item
        for item in actions
        for ref in (item.runtime_item_id, item.action_id, item.action_id.removeprefix("action:"))
    }
    selected_actions = [
        action_by_ref[action_id] for action_id in decision.selected_record_ids if action_id in action_by_ref
    ]
    selected_action_claim_ids = {action.action_id.removeprefix("action:") for action in selected_actions}
    selected_claims = [
        claim_by_ref[claim_id]
        for claim_id in decision.selected_record_ids
        if (claim_id in claim_by_ref and claim_by_ref[claim_id].claim_id not in selected_action_claim_ids)
    ]
    rejected_claims = [claim_by_ref[claim_id] for claim_id in decision.rejected_record_ids if claim_id in claim_by_ref]
    supporting_claims = [
        claim_by_ref[claim_id]
        for claim_id in decision.supporting_record_ids
        if (claim_id in claim_by_ref and claim_by_ref[claim_id].claim_id not in selected_action_claim_ids)
    ]
    context_claims = [claim_by_ref[claim_id] for claim_id in decision.context_record_ids if claim_id in claim_by_ref]
    selected_entities = [
        entity_by_ref[claim.subject_entity_id] for claim in selected_claims if claim.subject_entity_id in entity_by_ref
    ]
    selected_entities.extend(
        entity_by_ref[target_id]
        for action in selected_actions
        for target_id in action.target_entity_ids
        if target_id in entity_by_ref
    )
    uncertain_items = frozenset(
        _observed_reference(
            item_id,
            entity_by_ref=entity_by_ref,
            claim_by_ref=claim_by_ref,
            action_by_ref=action_by_ref,
            relations=relations,
            source_id_to_event_id=source_id_to_event_id,
        )
        for item_id in decision.uncertain_record_ids
        if _has_observed_reference(
            item_id,
            entity_by_ref=entity_by_ref,
            claim_by_ref=claim_by_ref,
            action_by_ref=action_by_ref,
            relations=relations,
        )
    )
    channel_record_ids: tuple[tuple[SemanticChannel, list[str]], ...] = (
        ("selected", decision.selected_record_ids),
        ("supporting", decision.supporting_record_ids),
        ("context", decision.context_record_ids),
        ("rejected", decision.rejected_record_ids),
        ("uncertain", decision.uncertain_record_ids),
    )
    unresolved_channel_ids: list[tuple[SemanticChannel, str]] = []
    for channel, item_ids in channel_record_ids:
        unresolved_channel_ids.extend(
            (channel, item_id)
            for item_id in item_ids
            if not _has_observed_reference(
                item_id,
                entity_by_ref=entity_by_ref,
                claim_by_ref=claim_by_ref,
                action_by_ref=action_by_ref,
                relations=relations,
            )
        )
    return _ObservedView(
        selected_entities=frozenset(_observed_entity(entity) for entity in selected_entities),
        selected_claims=frozenset(
            _observed_claim(claim, entity_by_ref, source_id_to_event_id) for claim in selected_claims
        ),
        supporting_claims=frozenset(
            _observed_claim(claim, entity_by_ref, source_id_to_event_id) for claim in supporting_claims
        ),
        context_claims=frozenset(
            _observed_claim(claim, entity_by_ref, source_id_to_event_id) for claim in context_claims
        ),
        rejected_claims=frozenset(
            _observed_claim(claim, entity_by_ref, source_id_to_event_id) for claim in rejected_claims
        ),
        relations=frozenset(
            _observed_relation(
                relation,
                entity_by_ref,
                claim_by_ref,
                source_id_to_event_id,
            )
            for relation in relations
            if relation.source != relation.target
        ),
        actions=frozenset(
            _observed_action(action, entity_by_ref, source_id_to_event_id) for action in selected_actions
        ),
        citations=frozenset(
            source_id_to_event_id.get(event_id, event_id)
            for claim in selected_claims
            for event_id in claim.evidence_event_ids
        )
        | frozenset(
            source_id_to_event_id.get(event_id, event_id)
            for action in selected_actions
            for event_id in action.evidence_event_ids
        ),
        uncertain_items=uncertain_items,
        unresolved_channel_ids=tuple(unresolved_channel_ids),
        abstention=decision.abstained,
    )


def _expected_entity(entity: LatentEntity) -> CanonicalEntity:
    return CanonicalEntity(
        _expected_text(entity.canonical_name),
        _expected_text(entity.entity_type),
    )


def _observed_entity(entity: RuntimeEntityGraphItemRow) -> CanonicalEntity:
    return CanonicalEntity(
        _observed_text(entity.canonical_name),
        _observed_text(entity.entity_type),
    )


def _expected_claim(
    claim: LatentClaim,
    entity_by_id: dict[str, LatentEntity],
) -> CanonicalClaim:
    object_entity = entity_by_id.get(claim.object.entity_id or "")
    return CanonicalClaim(
        subject=_expected_entity(entity_by_id[claim.subject.entity_id]),
        predicate=_expected_text(claim.predicate.predicate_id),
        object_kind="entity" if object_entity else "literal",
        object_value=(
            _expected_text(object_entity.canonical_name)
            if object_entity
            else _expected_text(claim.object.normalized_value or claim.object.value)
        ),
        object_entity_type=_expected_text(object_entity.entity_type) if object_entity else "",
        scope=_expected_text(claim.scope.scope_key),
        lifecycle=_expected_text(claim.lifecycle.state.value),
        valid_from=_expected_time(claim.lifecycle.valid_from),
        valid_to=_expected_time(claim.lifecycle.valid_to),
        provenance=tuple(sorted(claim.evidence.source_event_ids)),
    )


def _observed_claim(
    claim: RuntimeClaimGraphItemRow,
    entity_by_ref: dict[str, RuntimeEntityGraphItemRow],
    source_id_to_event_id: dict[str, str],
) -> CanonicalClaim:
    subject = entity_by_ref.get(claim.subject_entity_id)
    object_entity = entity_by_ref.get(claim.object_entity_id)
    return CanonicalClaim(
        subject=(_observed_entity(subject) if subject else CanonicalEntity(_observed_text(claim.subject), "unknown")),
        predicate=_observed_text(claim.predicate),
        object_kind="entity" if object_entity else "literal",
        object_value=(
            _observed_entity(object_entity).canonical_name
            if object_entity
            else _observed_text(claim.object_value or claim.object)
        ),
        object_entity_type=_observed_text(object_entity.entity_type) if object_entity else "",
        scope=_observed_text(claim.scope or "global"),
        lifecycle=_observed_text(claim.lifecycle_state.value),
        valid_from=_observed_time(claim.valid_from),
        valid_to=_observed_time(claim.valid_to),
        provenance=tuple(
            sorted(source_id_to_event_id.get(event_id, event_id) for event_id in claim.evidence_event_ids)
        ),
    )


def _expected_relation(
    relation: LatentRelation,
    entity_by_id: dict[str, LatentEntity],
    claim_by_id: dict[str, LatentClaim],
) -> CanonicalRelation:
    return CanonicalRelation(
        relation_type=_expected_text(relation.relation_type),
        source=_expected_endpoint(relation.source.endpoint_id, entity_by_id, claim_by_id),
        target=_expected_endpoint(relation.target.endpoint_id, entity_by_id, claim_by_id),
        directionality=relation.directionality,
    )


def _observed_relation(
    relation: RuntimeRelationGraphItemRow,
    entity_by_ref: dict[str, RuntimeEntityGraphItemRow],
    claim_by_ref: dict[str, RuntimeClaimGraphItemRow],
    source_id_to_event_id: dict[str, str],
) -> CanonicalRelation:
    return CanonicalRelation(
        relation_type=_observed_text(relation.relation_type.value),
        source=_observed_endpoint(
            relation.source,
            entity_by_ref,
            claim_by_ref,
            source_id_to_event_id,
        ),
        target=_observed_endpoint(
            relation.target,
            entity_by_ref,
            claim_by_ref,
            source_id_to_event_id,
        ),
        directionality=relation.directionality,
    )


def _expected_endpoint(
    endpoint_id: str,
    entity_by_id: dict[str, LatentEntity],
    claim_by_id: dict[str, LatentClaim],
) -> str:
    if endpoint_id in entity_by_id:
        return f"entity:{_expected_entity(entity_by_id[endpoint_id])!r}"
    if endpoint_id in claim_by_id:
        claim = _expected_claim(claim_by_id[endpoint_id], entity_by_id)
        return f"claim:{claim.identity!r}"
    return f"unknown:{_expected_text(endpoint_id)}"


def _observed_endpoint(
    endpoint_id: str,
    entity_by_ref: dict[str, RuntimeEntityGraphItemRow],
    claim_by_ref: dict[str, RuntimeClaimGraphItemRow],
    source_id_to_event_id: dict[str, str],
) -> str:
    if endpoint_id in entity_by_ref:
        return f"entity:{_observed_entity(entity_by_ref[endpoint_id])!r}"
    if endpoint_id in claim_by_ref:
        claim = _observed_claim(
            claim_by_ref[endpoint_id],
            entity_by_ref,
            source_id_to_event_id,
        )
        return f"claim:{claim.identity!r}"
    return f"unknown:{_observed_text(endpoint_id)}"


def _expected_reference(
    item_id: str,
    *,
    entity_by_id: dict[str, LatentEntity],
    claim_by_id: dict[str, LatentClaim],
    relation_by_id: dict[str, LatentRelation],
) -> str:
    if item_id in entity_by_id:
        return f"entity:{_expected_entity(entity_by_id[item_id])!r}"
    if item_id in claim_by_id:
        return f"claim:{_expected_claim(claim_by_id[item_id], entity_by_id)!r}"
    if item_id in relation_by_id:
        relation = _expected_relation(relation_by_id[item_id], entity_by_id, claim_by_id)
        return f"relation:{relation!r}"
    claim_id = item_id.removeprefix("action:")
    if item_id.startswith("action:") and claim_id in claim_by_id:
        return f"action:{_expected_action(item_id, claim_by_id, entity_by_id)!r}"
    return f"unknown:{_expected_text(item_id)}"


def _has_observed_reference(
    item_id: str,
    *,
    entity_by_ref: dict[str, RuntimeEntityGraphItemRow],
    claim_by_ref: dict[str, RuntimeClaimGraphItemRow],
    action_by_ref: dict[str, RuntimeActionGraphItemRow],
    relations: list[RuntimeRelationGraphItemRow],
) -> bool:
    return (
        item_id in entity_by_ref
        or item_id in claim_by_ref
        or item_id in action_by_ref
        or any(item_id == relation.runtime_item_id for relation in relations)
    )


def _observed_reference(
    item_id: str,
    *,
    entity_by_ref: dict[str, RuntimeEntityGraphItemRow],
    claim_by_ref: dict[str, RuntimeClaimGraphItemRow],
    action_by_ref: dict[str, RuntimeActionGraphItemRow],
    relations: list[RuntimeRelationGraphItemRow],
    source_id_to_event_id: dict[str, str] | None = None,
) -> str:
    provenance_map = source_id_to_event_id or {}
    if item_id in entity_by_ref:
        return f"entity:{_observed_entity(entity_by_ref[item_id])!r}"
    if item_id in claim_by_ref:
        return f"claim:{_observed_claim(claim_by_ref[item_id], entity_by_ref, provenance_map)!r}"
    if item_id in action_by_ref:
        return f"action:{_observed_action(action_by_ref[item_id], entity_by_ref, provenance_map)!r}"
    relation = next(item for item in relations if item.runtime_item_id == item_id)
    return f"relation:{_observed_relation(relation, entity_by_ref, claim_by_ref, provenance_map)!r}"


def _expected_action(
    action_id: str,
    claim_by_id: dict[str, LatentClaim],
    entity_by_id: dict[str, LatentEntity],
) -> CanonicalAction:
    claim_id = action_id.removeprefix("action:")
    claim = claim_by_id[claim_id]
    return CanonicalAction(
        action_type=_expected_text(claim.predicate.predicate_id),
        status=_expected_text(claim.object.normalized_value or claim.object.value),
        targets=(_expected_entity(entity_by_id[claim.subject.entity_id]),),
        provenance=tuple(sorted(claim.evidence.source_event_ids)),
    )


def _observed_action(
    action: RuntimeActionGraphItemRow,
    entity_by_ref: dict[str, RuntimeEntityGraphItemRow],
    source_id_to_event_id: dict[str, str],
) -> CanonicalAction:
    return CanonicalAction(
        action_type=_observed_text(action.action_type),
        status=_observed_text(action.status.value),
        targets=tuple(
            sorted(
                _observed_entity(entity_by_ref[target_id])
                for target_id in action.target_entity_ids
                if target_id in entity_by_ref
            )
        ),
        provenance=tuple(
            sorted(source_id_to_event_id.get(event_id, event_id) for event_id in action.evidence_event_ids)
        ),
    )
