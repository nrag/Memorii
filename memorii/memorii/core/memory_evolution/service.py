"""Runtime memory evolution service over the canonical memory plane."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from memorii.core.memory_evolution.claim_policy import ClaimLifecycleMutator
from memorii.core.memory_evolution.claim_queries import ClaimStateQueryService
from memorii.core.memory_evolution.confidence import ConfidenceAggregator
from memorii.core.memory_evolution.contradictions import ContradictionResolver
from memorii.core.memory_evolution.entity_resolution import EntityResolutionService
from memorii.core.memory_evolution.execution import (
    WorkStateSnapshot,
    action_event_from_extracted,
    reduce_work_states,
)
from memorii.core.memory_evolution.extraction import (
    EnglishRuleMemoryExtractor,
)
from memorii.core.memory_evolution.extraction_contracts import MemoryExtractionRunError, MemoryExtractor
from memorii.core.memory_evolution.graph import MemoryGraphProjector
from memorii.core.memory_evolution.graph_persistence import MemoryGraphStore, MemoryGraphValidator
from memorii.core.memory_evolution.graph_queries import MemoryGraphQueryService
from memorii.core.memory_evolution.modality import (
    ExtractionTriggerPolicy,
    SourceModalityClassifier,
    classify_and_mark_observation,
)
from memorii.core.memory_evolution.models import (
    ClaimLifecycleTransition,
    ClaimState,
    ContradictionSet,
    EntityMention,
    ExtractedAction,
    ExtractedClaim,
    ExtractionRun,
    ExtractionRunStatus,
    ExtractionTriggerMode,
    MemoryEvolutionResult,
    MemoryGraphSnapshot,
    MemoryScope,
    RetrievalView,
    SourceModality,
    SourceObservation,
    ValidationResult,
    ValidationVerdict,
)
from memorii.core.memory_evolution.mutations import (
    EvolutionMutationPlan,
    MemoryEvolutionMutationValidationError,
)
from memorii.core.memory_evolution.predicates import PredicateRegistry
from memorii.core.memory_evolution.query_analysis import EnglishLexicalQueryAnalyzer, QueryAnalyzer
from memorii.core.memory_evolution.record_projection import (
    record_from_contradiction_set,
    record_from_entity_link,
    record_from_temporal_anchor,
    source_observation_from_record,
)
from memorii.core.memory_evolution.retrieval_contracts import (
    MemoryQueryInput,
    ProductionRetrievalDecision,
)
from memorii.core.memory_evolution.retrieval_runtime import MemoryEvolutionRetrievalRuntime
from memorii.core.memory_evolution.state_repository import EvolutionStateRepository
from memorii.core.memory_evolution.temporal_contracts import (
    QueryTemporalFrame,
    QueryTemporalKind,
    RetrievalDecision,
    TemporalAnchor,
    TemporalAnchorCatalog,
)
from memorii.core.memory_evolution.validation import MemoryEvolutionValidator
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import MemoryPlanePrecondition, MemoryPlaneRevisionConflictError
from memorii.domain.enums import CommitStatus, MemoryDomain, TemporalValidityStatus

CompletionRecordFactory = Callable[[MemoryEvolutionResult], tuple[CanonicalMemoryRecord, ...]]


@dataclass(frozen=True)
class PreparedEvolution:
    observations: list[SourceObservation]
    extractable_observations: list[SourceObservation]
    deferred_observation_ids: list[str]
    skipped_observation_ids: list[str]
    run: ExtractionRun
    entities: list[EntityMention]
    claims: list[ExtractedClaim]
    actions: list[ExtractedAction]
    validation_results: dict[str, list[ValidationResult]]


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
        self._extractor = extractor or EnglishRuleMemoryExtractor()
        self._validator = validator or MemoryEvolutionValidator(predicate_registry=self._predicates)
        self._modality_classifier = modality_classifier or SourceModalityClassifier()
        self._trigger_policy = trigger_policy or ExtractionTriggerPolicy()
        self._now_provider = now_provider or (lambda: datetime.now(UTC))
        self._entity_resolver = entity_resolver or EntityResolutionService(now_provider=self._now_provider)
        confidence_aggregator = confidence_aggregator or ConfidenceAggregator()
        contradiction_resolver = contradiction_resolver or ContradictionResolver()
        self._graph_projector = graph_projector or MemoryGraphProjector()
        self._graph_store = graph_store or MemoryGraphStore(memory_plane=memory_plane)
        self._graph_validator = graph_validator or MemoryGraphValidator()
        self._graph_queries = MemoryGraphQueryService(
            graph_store=self._graph_store,
            now_provider=self._now_provider,
        )
        self._query_analyzer = query_analyzer or EnglishLexicalQueryAnalyzer()
        self._temporal_anchor_catalog = temporal_anchor_catalog or TemporalAnchorCatalog()
        self._state_repository = EvolutionStateRepository(memory_plane=memory_plane)
        self._state_repository.hydrate_temporal_anchors(self._temporal_anchor_catalog)
        self._claim_mutator = ClaimLifecycleMutator(
            memory_plane=self._memory_plane,
            predicate_registry=self._predicates,
            confidence_aggregator=confidence_aggregator,
            contradiction_resolver=contradiction_resolver,
            entity_resolver=self._entity_resolver,
            state_repository=self._state_repository,
            now_provider=self._now_provider,
        )
        self._claim_queries = ClaimStateQueryService(
            repository=self._state_repository,
            now_provider=self._now_provider,
        )
        self._retrieval_runtime = MemoryEvolutionRetrievalRuntime(
            claim_reader=self.retrieve_claim_states,
            entity_link_reader=self._state_repository.list_entity_links,
            action_reader=self._state_repository.list_actions,
            query_analyzer=self._query_analyzer,
            temporal_anchor_catalog=self._temporal_anchor_catalog,
            now_provider=self._now_provider,
        )

    def evolve_records(
        self,
        records: list[CanonicalMemoryRecord],
        *,
        defer_assertions: bool = False,
        completion_record_factory: CompletionRecordFactory | None = None,
        commit_preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> MemoryEvolutionResult:
        prepared = self.prepare_evolution(records, defer_assertions=defer_assertions)
        for attempt in range(3):
            try:
                with self._memory_plane.unit_of_work() as unit_of_work:
                    result = self._build_evolution_mutation(prepared)
                    if completion_record_factory is not None:
                        self._memory_plane.write_records(completion_record_factory(result))
                    plan = EvolutionMutationPlan(
                        expected_revision=unit_of_work.base_revision,
                        records=unit_of_work.pending_records,
                        graph_snapshot=MemoryGraphSnapshot(
                            snapshot_id=result.graph_snapshot_id or "",
                            nodes=result.graph_nodes,
                            edges=result.graph_edges,
                        ),
                    )
                    unit_of_work.commit(
                        records=plan.records,
                        expected_revision=plan.expected_revision,
                        preconditions=commit_preconditions,
                    )
                    return result
            except MemoryPlaneRevisionConflictError:
                if attempt == 2:
                    raise
        raise AssertionError("bounded evolution retry loop exited unexpectedly")

    def prepare_evolution(
        self,
        records: list[CanonicalMemoryRecord],
        *,
        defer_assertions: bool = False,
    ) -> PreparedEvolution:
        """Extract and validate once, outside the optimistic commit window."""

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
        skipped_observation_ids = [
            obs.source_id for obs in observations if obs.trigger_mode == ExtractionTriggerMode.SKIP
        ]
        run, entities, claims, actions = self._extractor.extract(extractable_observations)
        if run.status == ExtractionRunStatus.FAILED:
            raise MemoryExtractionRunError(run)
        validation_results = self._validator.validate_claims(claims=claims, observations=extractable_observations)
        run = run.model_copy(update={"validation_summary": self._validator.summary(validation_results)})
        return PreparedEvolution(
            observations=observations,
            extractable_observations=extractable_observations,
            deferred_observation_ids=deferred_observation_ids,
            skipped_observation_ids=skipped_observation_ids,
            run=run,
            entities=entities,
            claims=claims,
            actions=actions,
            validation_results=validation_results,
        )

    def _build_evolution_mutation(self, prepared: PreparedEvolution) -> MemoryEvolutionResult:
        observations = prepared.observations
        extractable_observations = prepared.extractable_observations
        deferred_observation_ids = prepared.deferred_observation_ids
        skipped_observation_ids = prepared.skipped_observation_ids
        run = prepared.run
        entities = prepared.entities
        claims = prepared.claims
        actions = prepared.actions
        validation_results = {claim_id: list(results) for claim_id, results in prepared.validation_results.items()}

        existing_entity_links = self._state_repository.list_entity_links()
        entity_resolution = self._entity_resolver.resolve_mentions(entities, existing_entity_links)
        entity_links = entity_resolution.links
        for link in entity_links:
            self._memory_plane.upsert_record(record_from_entity_link(link))

        claim_states: list[ClaimState] = []
        transitions: list[ClaimLifecycleTransition] = list(entity_resolution.transitions)
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
                state, record_id, contradiction_set = self._claim_mutator.retain_rejected_claim(
                    claim=claim,
                    validation_results=results,
                    source_observations=extractable_observations,
                    entity_links=entity_links,
                )
                claim_states.append(state)
                written_record_ids.append(record_id)
                if contradiction_set is not None:
                    contradiction_sets.append(contradiction_set)
                    contradiction_record = record_from_contradiction_set(contradiction_set)
                    self._memory_plane.upsert_record(contradiction_record)
                    written_record_ids.append(contradiction_record.memory_id)
                continue
            state, claim_transitions, record_id, contradiction_set = self._claim_mutator.apply_claim(
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
                contradiction_record = record_from_contradiction_set(contradiction_set)
                self._memory_plane.upsert_record(contradiction_record)
                written_record_ids.append(contradiction_record.memory_id)

        run = run.model_copy(update={"validation_summary": self._validator.summary(validation_results)})
        persistable_actions = [
            action
            for action in actions
            if not action.evidence_spans or any(span.source_id not in deferred_ids for span in action.evidence_spans)
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
            entity_identity_decisions=entity_resolution.decisions,
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
                "observations": self._state_repository.list_source_observations(),
                "entity_links": self._state_repository.list_entity_links(),
                "claim_states": self._state_repository.list_claim_states(),
                "actions": self._state_repository.list_actions(),
                "contradiction_sets": self._state_repository.list_contradiction_sets(),
            }
        )
        graph_snapshot = self._graph_projector.project_evolution_result(result=graph_input)
        graph_errors = self._graph_validator.validate_snapshot(graph_snapshot)
        if graph_errors:
            raise MemoryEvolutionMutationValidationError(graph_errors)
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

    def evolve_source_ids(
        self,
        source_ids: list[str],
        *,
        defer_assertions: bool = False,
        completion_record_factory: CompletionRecordFactory | None = None,
        commit_preconditions: tuple[MemoryPlanePrecondition, ...] = (),
    ) -> MemoryEvolutionResult:
        records = [
            record for source_id in source_ids if (record := self._memory_plane.get_record(source_id)) is not None
        ]
        return self.evolve_records(
            records,
            defer_assertions=defer_assertions,
            completion_record_factory=completion_record_factory,
            commit_preconditions=commit_preconditions,
        )

    def retrieve_claim_states(
        self,
        *,
        view: RetrievalView = RetrievalView.CURRENT,
        valid_at: datetime | None = None,
        predicate_id: str | None = None,
        subject_entity_id: str | None = None,
        temporal_frame: QueryTemporalFrame | None = None,
        request_scope: MemoryScope | None = None,
    ) -> list[ClaimState]:
        return self._claim_queries.retrieve(
            view=view,
            valid_at=valid_at,
            predicate_id=predicate_id,
            subject_entity_id=subject_entity_id,
            temporal_frame=temporal_frame,
            request_scope=request_scope,
        )

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

    def retrieve(self, request: MemoryQueryInput) -> ProductionRetrievalDecision:
        """Return the production query-conditioned memory decision."""

        return self._retrieval_runtime.retrieve(request)

    def retrieve_graph_snapshot(self) -> MemoryGraphSnapshot:
        return self._graph_queries.snapshot()

    def register_temporal_anchor(self, anchor: TemporalAnchor) -> None:
        """Register an evidence-backed interval after validating source provenance."""

        if not anchor.evidence:
            raise ValueError("temporal anchor requires at least one evidence span")
        records = [self._memory_plane.get_record(source_id) for source_id in anchor.source_ids]
        missing = [source_id for source_id, record in zip(anchor.source_ids, records, strict=True) if record is None]
        if missing:
            raise ValueError(f"temporal anchor references unknown sources: {sorted(missing)}")
        source_by_id = {record.memory_id: record for record in records if record is not None}
        expected_scope = anchor.scope
        for source_id in anchor.source_ids:
            record = source_by_id[source_id]
            if not (record.is_raw_event or record.domain == MemoryDomain.TRANSCRIPT):
                raise ValueError(f"temporal anchor source is not a source observation: {source_id}")
            record_scope = MemoryScope(
                task_id=record.task_id,
                session_id=record.session_id,
                user_id=record.user_id,
            )
            if record_scope != expected_scope:
                raise ValueError(f"temporal anchor source is outside scope: {source_id}")
        for evidence in anchor.evidence:
            record = source_by_id.get(evidence.source_id)
            if record is None or evidence.span.casefold() not in record.text.casefold():
                raise ValueError(f"temporal anchor evidence is not present in source: {evidence.source_id}")
        evidence_source_ids = {evidence.source_id for evidence in anchor.evidence}
        missing_evidence = sorted(set(anchor.source_ids) - evidence_source_ids)
        if missing_evidence:
            raise ValueError(f"temporal anchor sources without evidence: {missing_evidence}")
        self._temporal_anchor_catalog.register(anchor)
        self._memory_plane.upsert_record(record_from_temporal_anchor(anchor))

    def derive_work_state(self, *, actions: list[ExtractedAction] | None = None) -> WorkStateSnapshot:
        """Derive continuation state from immutable action history.

        The projection is deliberately read-only.  It does not mutate action
        records and can therefore be used by retrieval and agent adapters
        without changing the memory write path.
        """
        source_actions = actions if actions is not None else self._state_repository.list_actions()
        return reduce_work_states(action_event_from_extracted(action) for action in source_actions)

    def retrieve_current_truth_graph(
        self,
        *,
        subject_entity_id: str | None = None,
        predicate_id: str | None = None,
        temporal_frame: QueryTemporalFrame | None = None,
        evaluation_time: datetime | None = None,
    ) -> MemoryGraphSnapshot:
        return self._graph_queries.current_truth(
            subject_entity_id=subject_entity_id,
            predicate_id=predicate_id,
            temporal_frame=temporal_frame,
            evaluation_time=evaluation_time,
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
        return self._graph_queries.entity_subgraph(
            entity_id,
            include_historical=include_historical,
            include_conflicts=include_conflicts,
            temporal_frame=temporal_frame,
            evaluation_time=evaluation_time,
        )

    def retrieve_claim_lineage(self, claim_id: str) -> MemoryGraphSnapshot:
        return self._graph_queries.claim_lineage(claim_id)

    def retrieve_conflict_graph(self) -> MemoryGraphSnapshot:
        return self._graph_queries.conflict_graph()
