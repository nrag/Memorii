"""Runtime memory evolution service over the canonical memory plane."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid5, NAMESPACE_URL

from memorii.core.memory_evolution.confidence import ConfidenceAggregator
from memorii.core.memory_evolution.contradictions import ContradictionResolver
from memorii.core.memory_evolution.entity_resolution import EntityResolutionService
from memorii.core.memory_evolution.extraction import RuleMemoryExtractor
from memorii.core.memory_evolution.graph import (
    MemoryGraphProjector,
    MemoryGraphStore,
    MemoryGraphValidator,
    subgraph_from_ids,
)
from memorii.core.memory_evolution.modality import ExtractionTriggerPolicy, SourceModalityClassifier, classify_and_mark_observation
from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    ClaimTransitionType,
    ContradictionSet,
    EntityLinkState,
    ExtractionTriggerMode,
    ExtractedAction,
    ExtractedClaim,
    MemoryGraphEdgeType,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    MemoryEvolutionResult,
    RetrievalView,
    SourceModality,
    SourceObservation,
    ValidationResult,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry, source_trust_rank
from memorii.core.memory_evolution.validation import MemoryEvolutionValidator
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import CommitStatus, MemoryDomain, SourceType, TemporalValidityStatus


class MemoryEvolutionService:
    def __init__(
        self,
        *,
        memory_plane: MemoryPlaneService,
        predicate_registry: PredicateRegistry | None = None,
        extractor: RuleMemoryExtractor | None = None,
        validator: MemoryEvolutionValidator | None = None,
        modality_classifier: SourceModalityClassifier | None = None,
        trigger_policy: ExtractionTriggerPolicy | None = None,
        entity_resolver: EntityResolutionService | None = None,
        confidence_aggregator: ConfidenceAggregator | None = None,
        contradiction_resolver: ContradictionResolver | None = None,
        graph_projector: MemoryGraphProjector | None = None,
        graph_store: MemoryGraphStore | None = None,
        graph_validator: MemoryGraphValidator | None = None,
    ) -> None:
        self._memory_plane = memory_plane
        self._predicates = predicate_registry or PredicateRegistry()
        self._extractor = extractor or RuleMemoryExtractor()
        self._validator = validator or MemoryEvolutionValidator(predicate_registry=self._predicates)
        self._modality_classifier = modality_classifier or SourceModalityClassifier()
        self._trigger_policy = trigger_policy or ExtractionTriggerPolicy()
        self._entity_resolver = entity_resolver or EntityResolutionService()
        self._confidence_aggregator = confidence_aggregator or ConfidenceAggregator()
        self._contradiction_resolver = contradiction_resolver or ContradictionResolver()
        self._graph_projector = graph_projector or MemoryGraphProjector()
        self._graph_store = graph_store or MemoryGraphStore(memory_plane=memory_plane)
        self._graph_validator = graph_validator or MemoryGraphValidator()

    def evolve_records(self, records: list[CanonicalMemoryRecord]) -> MemoryEvolutionResult:
        observations = [
            classify_and_mark_observation(
                source_observation_from_record(record),
                classifier=self._modality_classifier,
                trigger_policy=self._trigger_policy,
            )
            for record in records
            if record.is_raw_event or record.domain == MemoryDomain.TRANSCRIPT
        ]
        immediate_observations = [obs for obs in observations if obs.trigger_mode == ExtractionTriggerMode.IMMEDIATE]
        deferred_observation_ids = [
            obs.source_id
            for obs in observations
            if obs.trigger_mode in {ExtractionTriggerMode.DEFERRED, ExtractionTriggerMode.BATCH_ONLY}
        ]
        skipped_observation_ids = [obs.source_id for obs in observations if obs.trigger_mode == ExtractionTriggerMode.SKIP]
        run, entities, claims, actions = self._extractor.extract(immediate_observations)
        validation_results = self._validator.validate_claims(claims=claims, observations=immediate_observations)
        run = run.model_copy(update={"validation_summary": self._validator.summary(validation_results)})

        entity_links = self._entity_resolver.resolve_mentions(entities, self._list_entity_links())
        for link in entity_links:
            self._memory_plane.upsert_record(_record_from_entity_link(link))

        claim_states: list[ClaimState] = []
        transitions: list[ClaimLifecycleTransition] = []
        contradiction_sets: list[ContradictionSet] = []
        written_record_ids: list[str] = []
        for claim in claims:
            results = validation_results.get(claim.claim_id, [])
            if not self._validator.accepted(results):
                continue
            state, claim_transitions, record_id, contradiction_set = self._apply_claim(
                claim=claim,
                validation_results=results,
                source_observations=immediate_observations,
                entity_links=entity_links,
            )
            claim_states.append(state)
            transitions.extend(claim_transitions)
            written_record_ids.append(record_id)
            if contradiction_set is not None:
                contradiction_sets.append(contradiction_set)
                contradiction_record = _record_from_contradiction_set(contradiction_set)
                self._memory_plane.upsert_record(contradiction_record)
                written_record_ids.append(contradiction_record.memory_id)

        for action in actions:
            record = CanonicalMemoryRecord(
                memory_id=f"mem:evolution:action:{action.action_id}",
                domain=MemoryDomain.EXECUTION,
                text=f"{action.action_type} {action.status}",
                content={
                    "memory_evolution_kind": "action",
                    "action": action.model_dump(mode="json"),
                },
                status=CommitStatus.COMMITTED,
                validity_status=TemporalValidityStatus.ACTIVE,
                source_kind="memory_evolution",
                timestamp=action.timestamp,
                is_raw_event=False,
                source_candidate_id=action.extraction_run_id,
            )
            self._memory_plane.stage_record(record)
            written_record_ids.append(record.memory_id)

        partial_result = MemoryEvolutionResult(
            extraction_run=run,
            entities=entities,
            claims=claims,
            actions=actions,
            observations=observations,
            entity_links=entity_links,
            contradiction_sets=contradiction_sets,
            deferred_observation_ids=deferred_observation_ids,
            skipped_observation_ids=skipped_observation_ids,
            validation_results=validation_results,
            claim_states=claim_states,
            transitions=transitions,
            written_record_ids=written_record_ids,
        )
        graph_input = partial_result.model_copy(
            update={
                "observations": self._list_source_observations(),
                "entity_links": self._list_entity_links(),
                "claim_states": self._list_claim_states(),
                "actions": self._list_actions(),
                "contradiction_sets": self._list_contradiction_sets(),
            }
        )
        graph_snapshot = self._graph_projector.project_evolution_result(result=graph_input)
        graph_errors = self._graph_validator.validate_snapshot(graph_snapshot)
        written_graph_ids = self._graph_store.upsert_snapshot(graph_snapshot)
        return partial_result.model_copy(
            update={
                "graph_nodes": graph_snapshot.nodes,
                "graph_edges": graph_snapshot.edges,
                "graph_snapshot_id": graph_snapshot.snapshot_id,
                "graph_validation_errors": graph_errors,
                "written_record_ids": [*partial_result.written_record_ids, *written_graph_ids],
            }
        )

    def evolve_source_ids(self, source_ids: list[str]) -> MemoryEvolutionResult:
        records = [record for source_id in source_ids if (record := self._memory_plane.get_record(source_id)) is not None]
        return self.evolve_records(records)

    def retrieve_claim_states(
        self,
        *,
        view: RetrievalView = RetrievalView.CURRENT,
        valid_at: datetime | None = None,
        predicate_id: str | None = None,
        subject_entity_id: str | None = None,
    ) -> list[ClaimState]:
        states = self._list_claim_states()
        if predicate_id is not None:
            states = [state for state in states if state.claim_key.predicate_id == predicate_id]
        if subject_entity_id is not None:
            states = [state for state in states if state.claim_key.subject_entity_id == subject_entity_id]

        if view == RetrievalView.CURRENT:
            return [state for state in states if state.lifecycle_state == ClaimLifecycleState.ACTIVE]
        if view == RetrievalView.HISTORICAL_AT:
            if valid_at is None:
                raise ValueError("valid_at is required for historical_at retrieval")
            return [state for state in states if _valid_at(state, valid_at)]
        if view == RetrievalView.CONFLICTS:
            return [state for state in states if state.conflict_with_claim_ids or state.lifecycle_state == ClaimLifecycleState.INVALIDATED]
        if view == RetrievalView.EVIDENCE_ONLY:
            return [state for state in states if state.evidence_spans]
        return states

    def retrieve_graph_snapshot(self) -> MemoryGraphSnapshot:
        return self._graph_store.snapshot()

    def retrieve_current_truth_graph(
        self,
        *,
        subject_entity_id: str | None = None,
        predicate_id: str | None = None,
    ) -> MemoryGraphSnapshot:
        snapshot = self.retrieve_graph_snapshot()
        matching_claims = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CLAIM
            and node.lifecycle_state == ClaimLifecycleState.ACTIVE.value
            and (predicate_id is None or node.properties.get("predicate_id") == predicate_id)
            and (subject_entity_id is None or node.properties.get("subject_entity_id") == subject_entity_id)
        }
        return _claim_subgraph(
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

    def retrieve_entity_subgraph(
        self,
        entity_id: str,
        *,
        include_historical: bool = False,
        include_conflicts: bool = False,
    ) -> MemoryGraphSnapshot:
        snapshot = self.retrieve_graph_snapshot()
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
            if include_historical or claim.lifecycle_state == ClaimLifecycleState.ACTIVE.value:
                claim_node_ids.add(claim.node_id)
        claim_graph = _claim_subgraph(
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

    def retrieve_claim_lineage(self, claim_id: str) -> MemoryGraphSnapshot:
        snapshot = self.retrieve_graph_snapshot()
        claim_node_ids = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CLAIM
            and (node.node_id == claim_id or node.canonical_id == claim_id)
        }
        edge_types = {
            MemoryGraphEdgeType.HAS_SUBJECT,
            MemoryGraphEdgeType.HAS_OBJECT,
            MemoryGraphEdgeType.HAS_LITERAL_OBJECT,
            MemoryGraphEdgeType.HAS_SCOPE,
            MemoryGraphEdgeType.OBSERVED_IN,
            MemoryGraphEdgeType.SUPERSEDES,
            MemoryGraphEdgeType.CONFLICTS_WITH,
            MemoryGraphEdgeType.CONTRADICTS,
        }
        return _claim_subgraph(snapshot=snapshot, claim_node_ids=claim_node_ids, include_edge_types=edge_types)

    def retrieve_conflict_graph(self) -> MemoryGraphSnapshot:
        snapshot = self.retrieve_graph_snapshot()
        node_ids = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CONTRADICTION_SET
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

    def _apply_claim(
        self,
        *,
        claim: ExtractedClaim,
        validation_results: list[ValidationResult],
        source_observations: list[SourceObservation],
        entity_links: list[EntityLinkState],
    ) -> tuple[ClaimState, list[ClaimLifecycleTransition], str, ContradictionSet | None]:
        now = datetime.now(UTC)
        policy = self._predicates.require(claim.claim_key.predicate_id)
        modality = _modality_for_claim(claim, source_observations)
        claim = claim.model_copy(update={"confidence": self._confidence_aggregator.initial_for_claim(claim, modality=modality)})
        subject_link = self._entity_resolver.link_for_entity(claim.claim_key.subject_entity_id, entity_links)
        object_link = self._entity_resolver.link_for_entity(claim.object_entity_id, entity_links)
        existing_active = [
            state
            for state in self._list_claim_states()
            if state.claim_key.stable_id() == claim.claim_key.stable_id()
            and state.lifecycle_state == ClaimLifecycleState.ACTIVE
        ]
        same_value = [state for state in existing_active if _norm(state.object_value) == _norm(claim.object_value)]
        different_value = [state for state in existing_active if _norm(state.object_value) != _norm(claim.object_value)]
        transitions: list[ClaimLifecycleTransition] = []

        if same_value:
            existing = same_value[0]
            confidence, update = self._confidence_aggregator.reinforce(
                existing=existing,
                claim=claim,
                modality=modality,
            )
            state = existing.model_copy(
                update={
                    "confidence": confidence,
                    "validation_results": [*existing.validation_results, *validation_results],
                    "evidence_spans": [*existing.evidence_spans, *claim.evidence_spans],
                    "confidence_history": [*existing.confidence_history, update],
                    "updated_at": now,
                }
            )
            transition = ClaimLifecycleTransition(
                transition_id=_stable_id("transition", f"{existing.claim_id}:reinforce:{claim.claim_id}"),
                transition_type=ClaimTransitionType.REINFORCE,
                claim_id=existing.claim_id,
                related_claim_ids=[claim.claim_id],
                rationale="new claim reinforces existing active claim",
            )
            record = _record_from_claim_state(state=state, source_candidate_id=claim.extraction_run_id)
            self._memory_plane.upsert_record(record)
            return state, [transition], record.memory_id, None
        elif policy.is_single_value and different_value:
            strongest = max(different_value, key=lambda state: _state_strength(policy.predicate_id, state))
            if _claim_strength(policy.predicate_id, claim) >= _state_strength(policy.predicate_id, strongest):
                lifecycle_state = ClaimLifecycleState.ACTIVE
                transition_type = ClaimTransitionType.SUPERSEDE
                related = [state.claim_id for state in different_value]
                supersedes = list(related)
                conflicts = list(related)
                rationale = "new single-value claim supersedes weaker or older active claims"
                for old_state in different_value:
                    self._mark_superseded(old_state=old_state, superseded_by_claim_id=claim.claim_id, valid_to=claim.valid_from or now)
            else:
                lifecycle_state = ClaimLifecycleState.INVALIDATED
                transition_type = ClaimTransitionType.INVALIDATE
                related = [strongest.claim_id]
                supersedes = []
                conflicts = [strongest.claim_id]
                rationale = "new single-value claim conflicts with a stronger active claim"
        else:
            lifecycle_state = ClaimLifecycleState.ACTIVE
            transition_type = ClaimTransitionType.CREATE if not existing_active else ClaimTransitionType.MERGE
            related = [state.claim_id for state in existing_active]
            supersedes = []
            conflicts = []
            rationale = "new claim creates or accumulates under predicate policy"

        state = ClaimState(
            claim_id=claim.claim_id,
            claim_key=claim.claim_key,
            object_value=claim.object_value,
            lifecycle_state=lifecycle_state,
            source_claim_id=claim.claim_id,
            confidence=claim.confidence,
            validation_results=validation_results,
            evidence_spans=claim.evidence_spans,
            supersedes_claim_ids=supersedes,
            conflict_with_claim_ids=conflicts,
            subject_link_id=subject_link.link_id if subject_link is not None else None,
            object_link_id=object_link.link_id if object_link is not None else None,
            valid_from=claim.valid_from,
            valid_to=claim.valid_to,
            created_at=now,
            updated_at=now,
        )
        transitions.append(
            ClaimLifecycleTransition(
                transition_id=_stable_id("transition", f"{claim.claim_id}:{transition_type.value}:{','.join(related)}"),
                transition_type=transition_type,
                claim_id=claim.claim_id,
                related_claim_ids=related,
                rationale=rationale,
            )
        )
        record = _record_from_claim_state(state=state, source_candidate_id=claim.extraction_run_id)
        self._memory_plane.stage_record(record)
        contradiction_set = self._contradiction_resolver.contradiction_for(
            policy=policy,
            claim=claim,
            existing_active=different_value,
            active_claim_id=state.claim_id if state.lifecycle_state == ClaimLifecycleState.ACTIVE else (strongest.claim_id if policy.is_single_value and different_value else None),
        )
        return state, transitions, record.memory_id, contradiction_set

    def _mark_superseded(
        self,
        *,
        old_state: ClaimState,
        superseded_by_claim_id: str,
        valid_to: datetime,
    ) -> None:
        updated = old_state.model_copy(
            update={
                "lifecycle_state": ClaimLifecycleState.SUPERSEDED,
                "superseded_by_claim_id": superseded_by_claim_id,
                "conflict_with_claim_ids": sorted({*old_state.conflict_with_claim_ids, superseded_by_claim_id}),
                "valid_to": valid_to,
                "updated_at": datetime.now(UTC),
            }
        )
        record = _record_from_claim_state(state=updated, source_candidate_id=updated.source_claim_id)
        self._memory_plane.upsert_record(record)

    def _list_claim_states(self) -> list[ClaimState]:
        states: list[ClaimState] = []
        for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC, MemoryDomain.USER, MemoryDomain.EXECUTION]):
            if record.content.get("memory_evolution_kind") != "claim_state":
                continue
            states.append(ClaimState.model_validate(record.content["claim_state"]))
        return states

    def _list_entity_links(self) -> list[EntityLinkState]:
        links: list[EntityLinkState] = []
        for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC]):
            if record.content.get("memory_evolution_kind") != "entity_link":
                continue
            links.append(EntityLinkState.model_validate(record.content["entity_link"]))
        return links

    def _list_contradiction_sets(self) -> list[ContradictionSet]:
        contradiction_sets: list[ContradictionSet] = []
        for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC]):
            if record.content.get("memory_evolution_kind") != "contradiction_set":
                continue
            contradiction_sets.append(ContradictionSet.model_validate(record.content["contradiction_set"]))
        return contradiction_sets

    def _list_actions(self) -> list[ExtractedAction]:
        actions: list[ExtractedAction] = []
        for record in self._memory_plane.list_records(domains=[MemoryDomain.EXECUTION]):
            if record.content.get("memory_evolution_kind") != "action":
                continue
            actions.append(ExtractedAction.model_validate(record.content["action"]))
        return actions

    def _list_source_observations(self) -> list[SourceObservation]:
        observations: list[SourceObservation] = []
        for record in self._memory_plane.list_records(domains=[MemoryDomain.TRANSCRIPT]):
            if not record.is_raw_event:
                continue
            observations.append(source_observation_from_record(record))
        return observations


def source_observation_from_record(record: CanonicalMemoryRecord) -> SourceObservation:
    return SourceObservation(
        source_id=record.memory_id,
        text=record.text,
        source_type=_source_type_from_record(record),
        timestamp=record.timestamp,
        domain=record.domain,
        session_id=record.session_id,
        task_id=record.task_id,
        user_id=record.user_id,
    )


def _record_from_entity_link(link: EntityLinkState) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:entity-link:{link.link_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"{link.canonical_entity_id} aliases: {', '.join(link.aliases)}",
        content={
            "memory_evolution_kind": "entity_link",
            "entity_link": link.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution",
        timestamp=link.updated_at,
    )


def _record_from_claim_state(*, state: ClaimState, source_candidate_id: str) -> CanonicalMemoryRecord:
    validity = {
        ClaimLifecycleState.ACTIVE: TemporalValidityStatus.ACTIVE,
        ClaimLifecycleState.EXPIRED: TemporalValidityStatus.EXPIRED,
        ClaimLifecycleState.SUPERSEDED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.INVALIDATED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.ARCHIVED: TemporalValidityStatus.INVALIDATED,
        ClaimLifecycleState.CANDIDATE: TemporalValidityStatus.UNKNOWN,
    }[state.lifecycle_state]
    domain = _domain_for_predicate(state.claim_key.predicate_id)
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:claim:{state.claim_id}",
        domain=domain,
        text=f"{state.claim_key.subject_entity_id} {state.claim_key.predicate_id} is {state.object_value}",
        content={
            "memory_evolution_kind": "claim_state",
            "claim_state": state.model_dump(mode="json"),
            "claim_key": state.claim_key.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=validity,
        source_kind="memory_evolution",
        timestamp=state.updated_at,
        valid_from=state.valid_from,
        valid_to=state.valid_to,
        source_candidate_id=source_candidate_id,
        supersedes_memory_ids=[f"mem:evolution:claim:{claim_id}" for claim_id in state.supersedes_claim_ids],
        conflict_with_memory_ids=[f"mem:evolution:claim:{claim_id}" for claim_id in state.conflict_with_claim_ids],
    )


def _record_from_contradiction_set(contradiction_set: ContradictionSet) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:contradiction:{contradiction_set.contradiction_set_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"Contradiction for {contradiction_set.claim_key.stable_id()}",
        content={
            "memory_evolution_kind": "contradiction_set",
            "contradiction_set": contradiction_set.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution",
        timestamp=contradiction_set.updated_at,
    )


def _source_type_from_record(record: CanonicalMemoryRecord) -> SourceType:
    source_kind = record.source_kind.lower()
    operation = str(record.content.get("operation") or "").lower()
    if operation in {"memory_write_longterm", "memory_write_user", "memory_write_dailylog"}:
        return SourceType.USER
    if operation in {"delegation_result"}:
        return SourceType.TOOL
    if "user" in source_kind:
        return SourceType.USER
    if "tool" in source_kind:
        return SourceType.TOOL
    if "environment" in source_kind:
        return SourceType.ENVIRONMENT
    if "agent" in source_kind:
        return SourceType.AGENT
    if "system" in source_kind:
        return SourceType.SYSTEM
    if record.domain == MemoryDomain.TRANSCRIPT:
        return SourceType.DERIVED
    return SourceType.DERIVED


def _domain_for_predicate(predicate_id: str) -> MemoryDomain:
    if predicate_id == "preference":
        return MemoryDomain.USER
    if predicate_id == "action_state":
        return MemoryDomain.EXECUTION
    return MemoryDomain.SEMANTIC


def _valid_at(state: ClaimState, valid_at: datetime) -> bool:
    if state.valid_from is not None and state.valid_from > valid_at:
        return False
    if state.valid_to is not None and state.valid_to < valid_at:
        return False
    return True


def _claim_strength(predicate_id: str, claim: ExtractedClaim) -> tuple[float, datetime]:
    source_type = claim.evidence_spans[0].source_type if claim.evidence_spans else SourceType.DERIVED
    policy = PredicateRegistry().require(predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return (min(1.0, claim.confidence.calibrated + trust_bonus), claim.valid_from or datetime.min.replace(tzinfo=UTC))


def _state_strength(predicate_id: str, state: ClaimState) -> tuple[float, datetime]:
    del predicate_id
    source_type = state.evidence_spans[0].source_type if state.evidence_spans else SourceType.DERIVED
    policy = PredicateRegistry().require(state.claim_key.predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return (min(1.0, state.confidence.calibrated + trust_bonus), state.valid_from or datetime.min.replace(tzinfo=UTC))


def _modality_for_claim(claim: ExtractedClaim, observations: list[SourceObservation]) -> SourceModality:
    observation_by_id = {observation.source_id: observation for observation in observations}
    for span in claim.evidence_spans:
        if (observation := observation_by_id.get(span.source_id)) is not None:
            return observation.modality
    return SourceModality.ASSERTION


def _norm(value: str) -> str:
    return " ".join(value.lower().strip(" .").split())


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}:{uuid5(NAMESPACE_URL, value)}"


def _claim_subgraph(
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
