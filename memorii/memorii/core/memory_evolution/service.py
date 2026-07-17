"""Runtime memory evolution service over the canonical memory plane."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from memorii.core.memory_evolution.confidence import ConfidenceAggregator
from memorii.core.memory_evolution.contradictions import ContradictionResolver
from memorii.core.memory_evolution.entity_resolution import EntityResolutionService
from memorii.core.memory_evolution.execution import (
    WorkStateSnapshot,
    WorkStateStatus,
    action_event_from_extracted,
    normalize_action_event_type,
    normalize_work_state_status,
    reduce_work_states,
    status_for_action_event,
)
from memorii.core.memory_evolution.extraction import MemoryExtractor, RuleMemoryExtractor
from memorii.core.memory_evolution.graph import (
    MemoryGraphProjector,
    MemoryGraphStore,
    MemoryGraphValidator,
    subgraph_from_ids,
)
from memorii.core.memory_evolution.modality import (
    ExtractionTriggerPolicy,
    SourceModalityClassifier,
    classify_and_mark_observation,
)
from memorii.core.memory_evolution.models import (
    ClaimLifecycleState,
    ClaimLifecycleTransition,
    ClaimState,
    ClaimTransitionType,
    ContradictionSet,
    EntityLinkState,
    ExtractedAction,
    ExtractedClaim,
    ExtractionTriggerMode,
    MemoryEvolutionResult,
    MemoryGraphEdgeType,
    MemoryGraphNode,
    MemoryGraphNodeType,
    MemoryGraphSnapshot,
    RetrievalView,
    SourceModality,
    SourceObservation,
    ValidationResult,
    ValidationVerdict,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry, source_trust_rank
from memorii.core.memory_evolution.retrieval import (
    MemoryQueryRequest,
    ProductionRetrievalDecision,
)
from memorii.core.memory_evolution.retrieval_runtime import MemoryEvolutionRetrievalRuntime
from memorii.core.memory_evolution.temporal import (
    ConservativeQueryAnalyzer,
    QueryAnalyzer,
    QueryTemporalFrame,
    QueryTemporalKind,
    RetrievalDecision,
    TemporalAnchor,
    TemporalAnchorCatalog,
    evaluate_temporal_eligibility,
)
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
        extractor: MemoryExtractor | None = None,
        validator: MemoryEvolutionValidator | None = None,
        modality_classifier: SourceModalityClassifier | None = None,
        trigger_policy: ExtractionTriggerPolicy | None = None,
        entity_resolver: EntityResolutionService | None = None,
        confidence_aggregator: ConfidenceAggregator | None = None,
        contradiction_resolver: ContradictionResolver | None = None,
        graph_projector: MemoryGraphProjector | None = None,
        graph_store: MemoryGraphStore | None = None,
        graph_validator: MemoryGraphValidator | None = None,
        query_analyzer: QueryAnalyzer | None = None,
        temporal_anchor_catalog: TemporalAnchorCatalog | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._memory_plane = memory_plane
        self._predicates = predicate_registry or PredicateRegistry()
        self._extractor = extractor or RuleMemoryExtractor()
        self._validator = validator or MemoryEvolutionValidator(predicate_registry=self._predicates)
        self._modality_classifier = modality_classifier or SourceModalityClassifier()
        self._trigger_policy = trigger_policy or ExtractionTriggerPolicy()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._entity_resolver = entity_resolver or EntityResolutionService(now_provider=self._now_provider)
        self._confidence_aggregator = confidence_aggregator or ConfidenceAggregator()
        self._contradiction_resolver = contradiction_resolver or ContradictionResolver()
        self._graph_projector = graph_projector or MemoryGraphProjector()
        self._graph_store = graph_store or MemoryGraphStore(memory_plane=memory_plane)
        self._graph_validator = graph_validator or MemoryGraphValidator()
        self._query_analyzer = query_analyzer or ConservativeQueryAnalyzer()
        self._temporal_anchor_catalog = temporal_anchor_catalog or TemporalAnchorCatalog()
        self._hydrate_temporal_anchors()
        self._retrieval_runtime = MemoryEvolutionRetrievalRuntime(
            claim_reader=self.retrieve_claim_states,
            entity_link_reader=self._list_entity_links,
            action_reader=self._list_actions,
            work_state_reader=self.derive_work_state,
            query_analyzer=self._query_analyzer,
            temporal_anchor_catalog=self._temporal_anchor_catalog,
            now_provider=self._now_provider,
        )

    def evolve_records(
        self,
        records: list[CanonicalMemoryRecord],
        *,
        defer_assertions: bool = False,
    ) -> MemoryEvolutionResult:
        observations = [
            classify_and_mark_observation(
                source_observation_from_record(record),
                classifier=self._modality_classifier,
                trigger_policy=self._trigger_policy,
            )
            for record in records
            if record.is_raw_event or record.domain == MemoryDomain.TRANSCRIPT
        ]
        if defer_assertions:
            observations = [
                observation.model_copy(update={"trigger_mode": ExtractionTriggerMode.DEFERRED})
                if observation.modality == SourceModality.ASSERTION
                else observation
                for observation in observations
            ]
        # Deferred observations may be extracted as candidates so their
        # provenance remains auditable, but the promotion gate below forces
        # every claim supported by one into INVALIDATED history. This keeps
        # candidate extraction separate from active-memory creation.
        extractable_observations = [
            obs
            for obs in observations
            if obs.trigger_mode in {ExtractionTriggerMode.IMMEDIATE, ExtractionTriggerMode.DEFERRED}
        ]
        deferred_observation_ids = [
            obs.source_id
            for obs in observations
            if obs.trigger_mode in {ExtractionTriggerMode.DEFERRED, ExtractionTriggerMode.BATCH_ONLY}
        ]
        skipped_observation_ids = [obs.source_id for obs in observations if obs.trigger_mode == ExtractionTriggerMode.SKIP]
        run, entities, claims, actions = self._extractor.extract(extractable_observations)
        validation_results = self._validator.validate_claims(claims=claims, observations=extractable_observations)
        run = run.model_copy(update={"validation_summary": self._validator.summary(validation_results)})

        existing_entity_links = self._list_entity_links()
        entity_links = self._entity_resolver.resolve_mentions(entities, existing_entity_links)
        for link in entity_links:
            self._memory_plane.upsert_record(_record_from_entity_link(link))

        claim_states: list[ClaimState] = []
        transitions: list[ClaimLifecycleTransition] = []
        for link in entity_links:
            if link.lineage_parent_entity_id is not None:
                transitions.append(
                    ClaimLifecycleTransition(
                        transition_id=_stable_id("transition", f"{link.link_id}:entity_split"),
                        transition_type=ClaimTransitionType.ENTITY_SPLIT,
                        claim_id=link.lineage_parent_entity_id,
                        related_claim_ids=[link.canonical_entity_id],
                        rationale="same-name entity was retained as a distinct lineage child",
                        timestamp=link.updated_at,
                    )
                )
        contradiction_sets: list[ContradictionSet] = []
        written_record_ids: list[str] = []
        deferred_ids = set(deferred_observation_ids)
        for claim in claims:
            results = validation_results.get(claim.claim_id, [])
            claim_source_ids = {span.source_id for span in claim.evidence_spans}
            if claim_source_ids & deferred_ids:
                results = [
                    *results,
                    ValidationResult(
                        validator_name="deferred_promotion_gate",
                        verdict=ValidationVerdict.FAIL,
                        score=0.0,
                        rationale="claim is supported by a deferred observation and cannot become active truth",
                    ),
                ]
                validation_results[claim.claim_id] = results
            if not self._validator.accepted(results):
                state, record_id, contradiction_set = self._retain_rejected_claim(
                    claim=claim,
                    validation_results=results,
                    source_observations=extractable_observations,
                    entity_links=entity_links,
                )
                claim_states.append(state)
                written_record_ids.append(record_id)
                if contradiction_set is not None:
                    contradiction_sets.append(contradiction_set)
                    contradiction_record = _record_from_contradiction_set(contradiction_set)
                    self._memory_plane.upsert_record(contradiction_record)
                    written_record_ids.append(contradiction_record.memory_id)
                continue
            state, claim_transitions, record_id, contradiction_set = self._apply_claim(
                claim=claim,
                validation_results=results,
                source_observations=extractable_observations,
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

        run = run.model_copy(update={"validation_summary": self._validator.summary(validation_results)})
        persistable_actions = [
            action
            for action in actions
            if not action.evidence_spans
            or any(span.source_id not in deferred_ids for span in action.evidence_spans)
        ]
        for action in persistable_actions:
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

    def _retain_rejected_claim(
        self,
        *,
        claim: ExtractedClaim,
        validation_results: list[ValidationResult],
        source_observations: list[SourceObservation],
        entity_links: list[EntityLinkState],
    ) -> tuple[ClaimState, str, ContradictionSet | None]:
        """Persist a rejected candidate as audit evidence, never as current truth.

        Validation is a gate on retrieval eligibility, not a license to erase
        the evidence that caused a conflict.  Keeping an INVALIDATED state
        gives the graph a deterministic contradiction/provenance trail while
        ``retrieve_claim_states(CURRENT)`` continues to exclude it.
        """
        now = self._now_provider()
        modality = _modality_for_claim(claim, source_observations)
        normalized_claim = claim.model_copy(
            update={"confidence": self._confidence_aggregator.initial_for_claim(claim, modality=modality)}
        )
        subject_link = self._entity_resolver.link_for_entity(claim.claim_key.subject_entity_id, entity_links)
        object_link = self._entity_resolver.link_for_entity(claim.object_entity_id, entity_links)
        existing_active = [
            state
            for state in self._list_claim_states()
            if state.claim_key.stable_id() == claim.claim_key.stable_id()
            and state.lifecycle_state == ClaimLifecycleState.ACTIVE
        ]
        different_value = [
            state for state in existing_active if _norm(state.object_value) != _norm(claim.object_value)
        ]
        strongest = max(
            different_value,
            key=lambda state: _state_strength(state, predicate_registry=self._predicates),
            default=None,
        )
        state = ClaimState(
            claim_id=normalized_claim.claim_id,
            claim_key=normalized_claim.claim_key,
            object_value=normalized_claim.object_value,
            lifecycle_state=ClaimLifecycleState.INVALIDATED,
            source_claim_id=normalized_claim.claim_id,
            confidence=normalized_claim.confidence,
            validation_results=validation_results,
            evidence_spans=normalized_claim.evidence_spans,
            conflict_with_claim_ids=[state.claim_id for state in different_value],
            subject_link_id=subject_link.link_id if subject_link is not None else None,
            object_link_id=object_link.link_id if object_link is not None else None,
            valid_from=normalized_claim.valid_from,
            valid_to=normalized_claim.valid_to,
            created_at=now,
            updated_at=now,
        )
        record = _record_from_claim_state(state=state, source_candidate_id=normalized_claim.extraction_run_id)
        self._memory_plane.stage_record(record)
        contradiction_set: ContradictionSet | None = None
        policy = self._predicates.get(normalized_claim.claim_key.predicate_id)
        if policy is not None and different_value:
            contradiction_set = self._contradiction_resolver.contradiction_for(
                policy=policy,
                claim=normalized_claim,
                existing_active=different_value,
                active_claim_id=strongest.claim_id if strongest is not None else None,
            )
        return state, record.memory_id, contradiction_set

    def evolve_source_ids(
        self,
        source_ids: list[str],
        *,
        defer_assertions: bool = False,
    ) -> MemoryEvolutionResult:
        records = [record for source_id in source_ids if (record := self._memory_plane.get_record(source_id)) is not None]
        return self.evolve_records(records, defer_assertions=defer_assertions)

    def retrieve_claim_states(
        self,
        *,
        view: RetrievalView = RetrievalView.CURRENT,
        valid_at: datetime | None = None,
        predicate_id: str | None = None,
        subject_entity_id: str | None = None,
        temporal_frame: QueryTemporalFrame | None = None,
    ) -> list[ClaimState]:
        if temporal_frame is None and view == RetrievalView.CURRENT:
            temporal_frame = QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                evaluation_time=self._now_provider(),
            )
        if temporal_frame is not None and temporal_frame.temporal_kind in {
            QueryTemporalKind.CURRENT,
            QueryTemporalKind.EXECUTION,
            QueryTemporalKind.BELIEF,
        } and temporal_frame.evaluation_time is None:
            temporal_frame = temporal_frame.model_copy(update={"evaluation_time": self._now_provider()})
        states = self._list_claim_states()
        if predicate_id is not None:
            states = [state for state in states if state.claim_key.predicate_id == predicate_id]
        if subject_entity_id is not None:
            states = [state for state in states if state.claim_key.subject_entity_id == subject_entity_id]
        if temporal_frame is not None and temporal_frame.scope_key is not None:
            states = [state for state in states if state.claim_key.scope_key in {temporal_frame.scope_key, "global"}]
        if temporal_frame is not None and temporal_frame.resolved_entity_ids:
            resolved_entity_ids = set(temporal_frame.resolved_entity_ids)
            links_by_id = {link.link_id: link.canonical_entity_id for link in self._list_entity_links()}
            states = [
                state
                for state in states
                if state.claim_key.subject_entity_id in resolved_entity_ids
                or links_by_id.get(state.object_link_id or "", state.object_link_id) in resolved_entity_ids
            ]

        if temporal_frame is not None:
            if temporal_frame.temporal_kind in {
                QueryTemporalKind.CURRENT,
                QueryTemporalKind.EXECUTION,
                QueryTemporalKind.BELIEF,
            }:
                view = RetrievalView.CURRENT
                if temporal_frame.evaluation_time is not None:
                    return [
                        state
                        for state in states
                        if evaluate_temporal_eligibility(
                            lifecycle_state=state.lifecycle_state.value,
                            valid_from=state.valid_from,
                            valid_to=state.valid_to,
                            temporal_kind=temporal_frame.temporal_kind,
                            evaluation_time=temporal_frame.evaluation_time,
                        ).eligible
                    ]
            elif temporal_frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
                return [
                    state
                    for state in states
                    if evaluate_temporal_eligibility(
                        lifecycle_state=state.lifecycle_state.value,
                        valid_from=state.valid_from,
                        valid_to=state.valid_to,
                        temporal_kind=temporal_frame.temporal_kind,
                        requested_from=temporal_frame.valid_from,
                        requested_to=temporal_frame.valid_to,
                    ).eligible
                ]
            elif temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS:
                return []

        if view == RetrievalView.CURRENT:
            evaluation_time = self._now_provider()
            return [
                state
                for state in states
                if evaluate_temporal_eligibility(
                    lifecycle_state=state.lifecycle_state.value,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    temporal_kind=QueryTemporalKind.CURRENT,
                    evaluation_time=evaluation_time,
                ).eligible
            ]
        if view == RetrievalView.HISTORICAL_AT:
            if valid_at is None:
                raise ValueError("valid_at is required for historical_at retrieval")
            return [
                state
                for state in states
                if evaluate_temporal_eligibility(
                    lifecycle_state=state.lifecycle_state.value,
                    valid_from=state.valid_from,
                    valid_to=state.valid_to,
                    temporal_kind=QueryTemporalKind.CURRENT,
                    evaluation_time=valid_at,
                ).eligible
            ]
        if view == RetrievalView.CONFLICTS:
            return [state for state in states if state.conflict_with_claim_ids or state.lifecycle_state == ClaimLifecycleState.INVALIDATED]
        if view == RetrievalView.EVIDENCE_ONLY:
            return [state for state in states if state.evidence_spans]
        return states

    def retrieve_claim_decision(self, *, temporal_frame: QueryTemporalFrame) -> RetrievalDecision:
        """Return an explicit retrieval decision for a resolved temporal frame."""
        if temporal_frame.temporal_kind == QueryTemporalKind.AMBIGUOUS:
            return RetrievalDecision(
                temporal_frame=temporal_frame,
                abstained=True,
                abstention_reason="temporal_frame_ambiguous",
            )
        states = self.retrieve_claim_states(temporal_frame=temporal_frame)
        record_ids = [state.claim_id for state in states]
        return RetrievalDecision(
            temporal_frame=temporal_frame,
            selected_record_ids=record_ids,
            supporting_record_ids=record_ids,
        )

    def retrieve(self, request: MemoryQueryRequest) -> ProductionRetrievalDecision:
        """Return the production query-conditioned memory decision."""

        return self._retrieval_runtime.retrieve(request)

    def retrieve_graph_snapshot(self) -> MemoryGraphSnapshot:
        return self._graph_store.snapshot()

    def register_temporal_anchor(self, anchor: TemporalAnchor, *, scope_key: str | None = None) -> None:
        """Register an evidence-backed interval after validating source provenance."""

        if not anchor.evidence:
            raise ValueError("temporal anchor requires at least one evidence span")
        records = [self._memory_plane.get_record(source_id) for source_id in anchor.source_ids]
        missing = [source_id for source_id, record in zip(anchor.source_ids, records, strict=True) if record is None]
        if missing:
            raise ValueError(f"temporal anchor references unknown sources: {sorted(missing)}")
        source_by_id = {record.memory_id: record for record in records if record is not None}
        expected_scope = scope_key or anchor.scope_key
        for source_id in anchor.source_ids:
            record = source_by_id[source_id]
            if not (record.is_raw_event or record.domain == MemoryDomain.TRANSCRIPT):
                raise ValueError(f"temporal anchor source is not a source observation: {source_id}")
            if expected_scope is not None and record.task_id not in {None, expected_scope}:
                raise ValueError(f"temporal anchor source is outside scope: {source_id}")
        for evidence in anchor.evidence:
            record = source_by_id.get(evidence.source_id)
            if record is None or evidence.span.casefold() not in record.text.casefold():
                raise ValueError(f"temporal anchor evidence is not present in source: {evidence.source_id}")
        evidence_source_ids = {evidence.source_id for evidence in anchor.evidence}
        missing_evidence = sorted(set(anchor.source_ids) - evidence_source_ids)
        if missing_evidence:
            raise ValueError(f"temporal anchor sources without evidence: {missing_evidence}")
        registered_anchor = anchor.model_copy(update={"scope_key": expected_scope}) if scope_key is not None else anchor
        self._temporal_anchor_catalog.register(registered_anchor)
        self._memory_plane.upsert_record(_record_from_temporal_anchor(registered_anchor))

    def derive_work_state(self, *, actions: list[ExtractedAction] | None = None) -> WorkStateSnapshot:
        """Derive continuation state from immutable action history.

        The projection is deliberately read-only.  It does not mutate action
        records and can therefore be used by retrieval and agent adapters
        without changing the memory write path.
        """
        source_actions = actions if actions is not None else self._list_actions()
        return reduce_work_states(action_event_from_extracted(action) for action in source_actions)

    def retrieve_current_truth_graph(
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
        if frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF} and frame.evaluation_time is None:
            frame = frame.model_copy(update={"evaluation_time": self._now_provider()})
        snapshot = self.retrieve_graph_snapshot()
        matching_claims = {
            node.node_id
            for node in snapshot.nodes
            if node.node_type == MemoryGraphNodeType.CLAIM
            and _graph_claim_matches_frame(
                node=node,
                frame=frame,
                include_historical=frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL},
            )
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
        elif frame is not None and frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF} and frame.evaluation_time is None:
            frame = frame.model_copy(update={"evaluation_time": self._now_provider()})
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
            if frame is None or _graph_claim_matches_frame(node=claim, frame=frame, include_historical=include_historical):
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
        now = self._now_provider()
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
            strongest = max(
                different_value,
                key=lambda state: _state_strength(state, predicate_registry=self._predicates),
            )
            if _claim_strength(claim, predicate_registry=self._predicates) >= _state_strength(
                strongest,
                predicate_registry=self._predicates,
            ):
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
                "updated_at": self._now_provider(),
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

    def _hydrate_temporal_anchors(self) -> None:
        for record in self._memory_plane.list_records(domains=[MemoryDomain.SEMANTIC]):
            if record.content.get("memory_evolution_kind") != "temporal_anchor":
                continue
            self._temporal_anchor_catalog.register(TemporalAnchor.model_validate(record.content["temporal_anchor"]))

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


def _continuation_status(action: ExtractedAction) -> WorkStateStatus:
    status = normalize_work_state_status(action.status)
    if status == WorkStateStatus.UNKNOWN:
        status = status_for_action_event(normalize_action_event_type(action.action_type))
    return status


def _graph_claim_matches_frame(*, node: MemoryGraphNode, frame: QueryTemporalFrame, include_historical: bool) -> bool:
    """Apply the same temporal semantics to graph claims as claim retrieval."""
    properties = node.properties
    lifecycle_state = node.lifecycle_state
    if frame.resolved_entity_ids:
        resolved_entity_ids = set(frame.resolved_entity_ids)
        if not ({properties.get("subject_entity_id", ""), properties.get("object_entity_id", ""), properties.get("object_link_id", "")} & resolved_entity_ids):
            return False
    if frame.scope_key is not None and properties.get("scope_key") not in {frame.scope_key, "global"}:
        return False
    if frame.temporal_kind in {QueryTemporalKind.CURRENT, QueryTemporalKind.EXECUTION, QueryTemporalKind.BELIEF}:
        return evaluate_temporal_eligibility(
            lifecycle_state=lifecycle_state,
            valid_from=_parse_graph_datetime(properties.get("valid_from")),
            valid_to=_parse_graph_datetime(properties.get("valid_to")),
            temporal_kind=frame.temporal_kind,
            evaluation_time=frame.evaluation_time,
        ).eligible
    if frame.temporal_kind in {QueryTemporalKind.HISTORICAL, QueryTemporalKind.INTERVAL}:
        return evaluate_temporal_eligibility(
            lifecycle_state=lifecycle_state,
            valid_from=_parse_graph_datetime(properties.get("valid_from")),
            valid_to=_parse_graph_datetime(properties.get("valid_to")),
            temporal_kind=frame.temporal_kind,
            requested_from=frame.valid_from,
            requested_to=frame.valid_to,
        ).eligible
    return False


def _graph_interval_contains(properties: dict[str, str], evaluation_time: datetime) -> bool:
    valid_from = _parse_graph_datetime(properties.get("valid_from"))
    valid_to = _parse_graph_datetime(properties.get("valid_to"))
    return not (valid_from is not None and valid_from > evaluation_time) and not (
        valid_to is not None and valid_to <= evaluation_time
    )


def _parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


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


def _record_from_temporal_anchor(anchor: TemporalAnchor) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=f"mem:evolution:temporal-anchor:{anchor.anchor_id}",
        domain=MemoryDomain.SEMANTIC,
        text=f"Temporal anchor {anchor.anchor_id}: {', '.join(anchor.names)}",
        content={
            "memory_evolution_kind": "temporal_anchor",
            "temporal_anchor": anchor.model_dump(mode="json"),
        },
        status=CommitStatus.COMMITTED,
        validity_status=TemporalValidityStatus.ACTIVE,
        source_kind="memory_evolution",
        timestamp=anchor.valid_to,
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


def _claim_strength(
    claim: ExtractedClaim,
    *,
    predicate_registry: PredicateRegistry,
) -> tuple[float, datetime]:
    source_type = claim.evidence_spans[0].source_type if claim.evidence_spans else SourceType.DERIVED
    policy = predicate_registry.require(claim.claim_key.predicate_id)
    trust_bonus = source_trust_rank(policy, source_type) / max(1, len(policy.trust_precedence)) * 0.05
    return (min(1.0, claim.confidence.calibrated + trust_bonus), claim.valid_from or datetime.min.replace(tzinfo=UTC))


def _state_strength(
    state: ClaimState,
    *,
    predicate_registry: PredicateRegistry,
) -> tuple[float, datetime]:
    source_type = state.evidence_spans[0].source_type if state.evidence_spans else SourceType.DERIVED
    policy = predicate_registry.require(state.claim_key.predicate_id)
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
