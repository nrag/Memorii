from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution import (
    GraphAuditRequest,
    MemoryEvolutionService,
    MemoryQueryRequest,
)
from memorii.core.memory_evolution.graph_persistence import MemoryGraphStore
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimState,
    ConfidenceComponents,
    EntityLinkState,
    ExtractedAction,
    MemoryScope,
    RetrievalView,
)
from memorii.core.memory_evolution.query_analysis import (
    EnglishLexicalQueryAnalyzer,
    StructuredQueryAnalyzer,
)
from memorii.core.memory_evolution.retrieval import rank_claims
from memorii.core.memory_evolution.retrieval_contracts import ResolvedMemoryQuery
from memorii.core.memory_evolution.retrieval_runtime import MemoryEvolutionRetrievalRuntime
from memorii.core.memory_evolution.temporal_contracts import (
    QueryAnalysis,
    QueryScopeKind,
    QueryTemporalFrame,
    QueryTemporalKind,
    RetrievalDecision,
    TemporalAnchor,
    TemporalAnchorCatalog,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


def _record(memory_id: str, text: str, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        timestamp=timestamp,
        is_raw_event=True,
    )


def test_production_retrieval_separates_current_and_historical_truth() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    january = datetime(2026, 1, 10, tzinfo=UTC)
    march = datetime(2026, 3, 10, tzinfo=UTC)
    for record in (
        _record("tx:alice", "Atlas migration owner is Alice.", january),
        _record("tx:bob", "Atlas migration owner is Bob.", march),
    ):
        service.evolve_records([record])

    current = service.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas migration now?",
            reference_time=datetime(2026, 3, 20, tzinfo=UTC),
        )
    )
    historical = service.retrieve(
        MemoryQueryRequest(
            query="Who owned the Atlas migration in January?",
            reference_time=datetime(2026, 3, 20, tzinfo=UTC),
        )
    )
    current_with_conflicts = service.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas migration now?",
            reference_time=datetime(2026, 3, 20, tzinfo=UTC),
            include_conflicts=True,
        )
    )

    assert current.selected_record_ids
    assert current.supporting_record_ids == current.selected_record_ids
    assert historical.selected_record_ids
    assert current.selected_record_ids != historical.selected_record_ids
    assert set(current.rejected_record_ids)
    assert current_with_conflicts.selected_record_ids == current.selected_record_ids
    assert current_with_conflicts.rejected_record_ids == current.rejected_record_ids
    assert current.context_items
    assert any(item.channel == "selected" for item in current.context_items)
    assert current.evidence
    assert {item.claim_id for item in current.evidence} <= {item.claim_id for item in current.context_items}
    assert service.retrieve_claim_states(view=RetrievalView.CURRENT)
    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    assert states[current.selected_record_ids[0]].object_value == "Bob"
    assert states[historical.selected_record_ids[0]].object_value == "Alice"


def test_production_retrieval_abstains_on_ambiguous_entity_anchor() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records([_record("tx:project", "Atlas migration owner is Bob.", datetime(2026, 1, 1, tzinfo=UTC))])
    service.evolve_records([_record("tx:service", "Atlas service owner is Iris.", datetime(2026, 1, 2, tzinfo=UTC))])

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Which Atlas owner is current?",
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    assert decision.abstained is True
    assert decision.abstention_reason == "entity_resolution_ambiguous"


def test_graph_audit_preserves_explicit_multi_entity_query() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records(
        [_record("tx:project", "Atlas migration owner is Bob.", datetime(2026, 1, 1, tzinfo=UTC))]
    )
    service.evolve_records(
        [_record("tx:service", "Atlas service owner is Iris.", datetime(2026, 1, 2, tzinfo=UTC))]
    )

    decision = service.retrieve(
        GraphAuditRequest(
            query="Reconstruct the Atlas project and Atlas service ownership graph.",
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
            purpose="graph_audit",
            scope_mode="full",
        )
    )

    snapshot = service.retrieve_graph_snapshot()
    expected_entities = {
        node.properties["canonical_entity_id"]
        for node in snapshot.nodes
        if node.node_type.value == "entity"
        and node.properties.get("entity_type") in {"project", "service"}
    }
    assert decision.abstained is False
    assert expected_entities <= set(decision.temporal_frame.resolved_entity_ids)
    states = {
        state.claim_id: state
        for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    }
    assert {states[claim_id].object_value for claim_id in decision.selected_record_ids} >= {"Bob", "Iris"}


def test_graph_audit_preserves_explicit_belief_candidates() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    service.evolve_records(
        [_record("tx:bob", "Atlas migration owner is Bob.", datetime(2026, 1, 1, tzinfo=UTC))]
    )
    service.evolve_records(
        [_record("tx:alice", "Atlas migration owner is Alice.", datetime(2026, 1, 2, tzinfo=UTC))]
    )

    decision = service.retrieve(
        GraphAuditRequest(
            query="Rank the competing belief claims that Bob and Alice own the Atlas migration.",
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
            purpose="graph_audit",
            scope_mode="full",
            include_conflicts=True,
        )
    )

    states = {
        state.claim_id: state
        for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    }
    selected_values = {states[claim_id].object_value for claim_id in decision.selected_record_ids}
    rejected_values = {states[claim_id].object_value for claim_id in decision.rejected_record_ids}
    assert decision.abstained is False
    assert decision.temporal_frame.temporal_kind == QueryTemporalKind.BELIEF
    snapshot = service.retrieve_graph_snapshot()
    selected_entity_names = {
        node.properties["normalized_name"]
        for node in snapshot.nodes
        if node.node_type.value == "entity"
        and node.properties.get("canonical_entity_id") in decision.temporal_frame.resolved_entity_ids
    }
    assert {"bob", "alice"} <= selected_entity_names
    assert selected_values == {"Alice"}
    assert "Bob" in rejected_values


def test_relation_condition_resolves_split_entity_from_passive_object_evidence() -> None:
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    project = EntityLinkState(
        link_id="link:atlas-project",
        mention_text="Atlas Billing Migration",
        normalized_name="atlas billing migration",
        canonical_entity_id="entity:atlas-project",
        aliases=["Atlas"],
        entity_type="project",
        confidence=1.0,
    )
    service = EntityLinkState(
        link_id="link:atlas-service",
        mention_text="Atlas Platform Service",
        normalized_name="atlas platform service",
        canonical_entity_id="entity:atlas-service",
        aliases=["Atlas service"],
        entity_type="service",
        confidence=1.0,
    )
    carol = EntityLinkState(
        link_id="link:carol",
        mention_text="Carol",
        normalized_name="carol",
        canonical_entity_id="entity:carol",
        entity_type="person",
        confidence=1.0,
    )
    owen = EntityLinkState(
        link_id="link:owen",
        mention_text="Owen",
        normalized_name="owen",
        canonical_entity_id="entity:owen",
        entity_type="person",
        confidence=1.0,
    )
    confidence = ConfidenceComponents(
        extraction=1.0,
        evidence=1.0,
        source_trust=1.0,
        calibrated=1.0,
    )
    states = [
        ClaimState(
            claim_id="claim:project-owner",
            claim_key=ClaimKey(subject_entity_id="extracted:atlas-project", predicate_id="owner"),
            object_value="Owen",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="source:project-owner",
            confidence=confidence,
            subject_link_id=project.link_id,
            object_link_id=owen.link_id,
            valid_from=timestamp,
        ),
        ClaimState(
            claim_id="claim:service-owner",
            claim_key=ClaimKey(subject_entity_id="extracted:atlas-service", predicate_id="owner"),
            object_value="Carol",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="source:service-owner",
            confidence=confidence,
            subject_link_id=service.link_id,
            object_link_id=carol.link_id,
            valid_from=timestamp,
        ),
    ]
    runtime = MemoryEvolutionRetrievalRuntime(
        claim_reader=lambda **_kwargs: states,
        entity_link_reader=lambda: [project, service, carol, owen],
        action_reader=lambda: [],
        query_analyzer=EnglishLexicalQueryAnalyzer(),
        temporal_anchor_catalog=TemporalAnchorCatalog(),
        now_provider=lambda: timestamp,
    )

    decision = runtime.retrieve(
        MemoryQueryRequest(
            query="Which Atlas entity is owned by Carol?",
            reference_time=timestamp,
        )
    )

    assert decision.abstained is False
    assert decision.selected_record_ids == ["claim:service-owner"]
    assert decision.graph_pattern_resolution is not None
    assert decision.graph_pattern_resolution.subject_entity_id == service.canonical_entity_id
    assert decision.graph_pattern_resolution.matched_claim_ids == ["claim:service-owner"]
    assert decision.graph_pattern_resolution.resolution_method.value == "lexical_participant_fallback"
    assert decision.temporal_frame is not None
    assert decision.temporal_frame.resolution_confidence == 0.65
    assert decision.temporal_frame.resolution_confidence_source == "lexical_participant_fallback"
    assert decision.context_record_ids == []
    assert decision.rejected_record_ids == ["claim:project-owner"]

    contrastive = runtime.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas billing migration, not the service?",
            reference_time=timestamp,
        )
    )

    assert contrastive.abstained is False
    assert contrastive.selected_record_ids == ["claim:project-owner"]
    assert contrastive.rejected_record_ids == ["claim:service-owner"]


def test_retrieval_channel_contract_allows_selected_support_only() -> None:
    decision = RetrievalDecision(
        temporal_frame=QueryTemporalFrame(),
        selected_record_ids=["claim:selected"],
        supporting_record_ids=["claim:selected"],
        context_record_ids=["claim:context"],
        rejected_record_ids=["claim:rejected"],
    )

    assert decision.selected_record_ids == decision.supporting_record_ids


@pytest.mark.parametrize(
    "update",
    [
        {"supporting_record_ids": []},
        {"context_record_ids": ["claim:selected"]},
        {"rejected_record_ids": ["claim:selected"]},
        {
            "context_record_ids": ["claim:shared"],
            "rejected_record_ids": ["claim:shared"],
        },
    ],
)
def test_retrieval_channel_contract_rejects_missing_support_or_role_overlap(
    update: dict[str, list[str]],
) -> None:
    payload = {
        "temporal_frame": QueryTemporalFrame(),
        "selected_record_ids": ["claim:selected"],
        "supporting_record_ids": ["claim:selected"],
        **update,
    }

    with pytest.raises(ValueError):
        RetrievalDecision(**payload)


def test_frozen_graph_retrieval_places_subject_definition_in_context() -> None:
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    confidence = ConfidenceComponents(
        extraction=1.0,
        evidence=1.0,
        source_trust=1.0,
        calibrated=1.0,
    )
    states = [
        ClaimState(
            claim_id="claim:owner",
            claim_key=ClaimKey(subject_entity_id="raw:atlas", predicate_id="owner"),
            object_value="Alice",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="source:owner",
            confidence=confidence,
            valid_from=timestamp,
        ),
        ClaimState(
            claim_id="claim:definition",
            claim_key=ClaimKey(subject_entity_id="raw:atlas", predicate_id="entity_type"),
            object_value="project",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="source:definition",
            confidence=confidence,
            valid_from=timestamp,
        ),
    ]
    frame = QueryTemporalFrame(
        temporal_kind=QueryTemporalKind.CURRENT,
        evaluation_time=timestamp,
        resolved_entity_ids=["entity:atlas"],
    )
    request = ResolvedMemoryQuery(
        query="Who owns Atlas?",
        reference_time=timestamp,
        query_analysis=QueryAnalysis(
            temporal_frame=frame,
            predicate_id="owner",
            subject_entity_id="entity:atlas",
        ),
        temporal_frame=frame,
        predicate_id="owner",
        subject_entity_id="entity:atlas",
    )

    decision = rank_claims(
        request=request,
        frame=frame,
        states=states,
        subject_entity_by_claim={
            "claim:owner": "entity:atlas",
            "claim:definition": "entity:atlas",
        },
    )

    assert decision.selected_record_ids == ["claim:owner"]
    assert decision.supporting_record_ids == ["claim:owner"]
    assert decision.context_record_ids == ["claim:definition"]
    assert decision.rejected_record_ids == []


def test_frozen_graph_scope_shadowing_uses_canonical_subject_identity() -> None:
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    confidence = ConfidenceComponents(
        extraction=1.0,
        evidence=1.0,
        source_trust=1.0,
        calibrated=1.0,
    )
    states = [
        ClaimState(
            claim_id="claim:global",
            claim_key=ClaimKey(
                subject_entity_id="raw:atlas-global",
                predicate_id="owner",
                scope=MemoryScope(),
            ),
            object_value="GlobalOwner",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="source:global",
            confidence=confidence,
            valid_from=timestamp,
        ),
        ClaimState(
            claim_id="claim:task",
            claim_key=ClaimKey(
                subject_entity_id="raw:atlas-task",
                predicate_id="owner",
                scope=MemoryScope(task_id="task:incident"),
            ),
            object_value="TaskOwner",
            lifecycle_state=ClaimLifecycleState.ACTIVE,
            source_claim_id="source:task",
            confidence=confidence,
            valid_from=timestamp,
        ),
    ]
    frame = QueryTemporalFrame(
        temporal_kind=QueryTemporalKind.CURRENT,
        evaluation_time=timestamp,
        resolved_entity_ids=["entity:atlas"],
        scope_kind=QueryScopeKind.TASK,
        scope_key="task:incident",
    )
    request = ResolvedMemoryQuery(
        query="Who owns Atlas?",
        reference_time=timestamp,
        scope=MemoryScope(task_id="task:incident"),
        query_analysis=QueryAnalysis(
            temporal_frame=frame,
            predicate_id="owner",
            subject_entity_id="entity:atlas",
        ),
        temporal_frame=frame,
        predicate_id="owner",
        subject_entity_id="entity:atlas",
    )

    decision = rank_claims(
        request=request,
        frame=frame,
        states=states,
        subject_entity_by_claim={
            "claim:global": "entity:atlas",
            "claim:task": "entity:atlas",
        },
    )

    assert decision.selected_record_ids == ["claim:task"]
    assert decision.supporting_record_ids == ["claim:task"]
    assert decision.context_record_ids == ["claim:global"]
    assert decision.rejected_record_ids == []


def test_public_query_request_rejects_caller_supplied_semantic_analysis() -> None:
    with pytest.raises(ValueError, match="query_analysis"):
        MemoryQueryRequest.model_validate(
            {
                "query": "Who owns Atlas?",
                "query_analysis": {"temporal_frame": {"temporal_kind": "current"}},
            }
        )


def test_explicit_global_scope_is_valid_for_natural_query() -> None:
    request = MemoryQueryRequest(query="Who owns Atlas?", scope=MemoryScope())

    assert request.scope_key == "global"


def test_global_request_rejects_analyzer_selected_task_scope() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records(
        [
            _record(
                "tx:secret",
                "Atlas owner is Secret.",
                datetime(2026, 1, 1, tzinfo=UTC),
            ).model_copy(update={"task_id": "task:secret"})
        ]
    )

    service = MemoryEvolutionService(
        memory_plane=plane,
        query_analyzer=StructuredQueryAnalyzer(
            lambda **_kwargs: {
                "predicate_id": "owner",
                "temporal_intent": "current",
                "temporal_expression": {"expression_kind": "current"},
            },
            analyzer_name="malicious-scope-analyzer",
            analyzer_version="1",
        ),
    )
    decision = service.retrieve(MemoryQueryRequest(query="Who owns Atlas?"))

    assert decision.abstained is True
    assert decision.resolution_status == "ambiguous"
    assert decision.selected_record_ids == []


def test_global_request_does_not_rank_task_scoped_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records(
        [
            _record(
                "tx:secret",
                "Atlas owner is Secret.",
                datetime(2026, 1, 1, tzinfo=UTC),
            ).model_copy(update={"task_id": "task:secret"})
        ]
    )

    decision = service.retrieve(MemoryQueryRequest(query="Who owns Atlas?"))

    assert decision.selected_record_ids == []


def test_graph_store_reports_malformed_persisted_rows() -> None:
    plane = MemoryPlaneService()
    plane.upsert_record(
        CanonicalMemoryRecord(
            memory_id="graph:bad-node",
            domain=MemoryDomain.SEMANTIC,
            text="malformed graph node",
            content={"memory_evolution_kind": "graph_node", "graph_node": {"node_id": "missing-required-fields"}},
            status=CommitStatus.COMMITTED,
            source_kind="memory_evolution",
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    snapshot = MemoryGraphStore(memory_plane=plane).snapshot()

    assert "skipped_node_count=1" in snapshot.validation_errors


def test_graph_store_skips_unknown_persisted_lifecycle_state() -> None:
    plane = MemoryPlaneService()
    plane.upsert_record(
        CanonicalMemoryRecord(
            memory_id="mem:evolution:graph-node:unknown-lifecycle",
            domain=MemoryDomain.SEMANTIC,
            text="invalid lifecycle graph node",
            content={
                "memory_evolution_kind": "graph_node",
                "graph_node": {
                    "node_id": "graph:node:claim:invalid-lifecycle",
                    "node_type": "claim",
                    "label": "invalid lifecycle",
                    "lifecycle_state": "corrupt-or-future-state",
                    "confidence": 0.8,
                    "payload_ref": "claim:invalid-lifecycle",
                },
            },
            status=CommitStatus.COMMITTED,
            source_kind="test",
            is_raw_event=False,
        )
    )
    service = MemoryEvolutionService(memory_plane=plane)

    snapshot = service.retrieve_graph_snapshot()

    assert all(node.node_id != "graph:node:claim:invalid-lifecycle" for node in snapshot.nodes)
    assert "skipped_node_count=1" in snapshot.validation_errors


def test_scoped_retrieval_prefers_exact_scope_over_global_fallback() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records([_record("tx:global", "Atlas migration owner is Global.", datetime(2026, 1, 1, tzinfo=UTC))])
    service.evolve_records(
        [
            _record("tx:incident", "Atlas migration owner is Incident.", datetime(2026, 1, 2, tzinfo=UTC)).model_copy(
                update={"task_id": "task:incident"}
            )
        ]
    )

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas migration?",
            scope=MemoryScope(task_id="task:incident"),
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    assert decision.selected_record_ids
    assert states[decision.selected_record_ids[0]].object_value == "Incident"
    assert all(states[claim_id].object_value != "Global" for claim_id in decision.selected_record_ids)


def test_task_retrieval_can_fall_back_to_readable_user_scope() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records(
        [
            _record(
                "tx:user",
                "Atlas migration owner is UserDefault.",
                datetime(2026, 1, 1, tzinfo=UTC),
            ).model_copy(update={"user_id": "user:one"})
        ]
    )

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas migration?",
            scope=MemoryScope(
                task_id="task:incident",
                session_id="session:incident",
                user_id="user:one",
            ),
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    assert [states[claim_id].object_value for claim_id in decision.selected_record_ids] == ["UserDefault"]


def test_task_scope_shadows_readable_user_scope_for_same_claim_identity() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records(
        [
            _record(
                "tx:user",
                "Atlas migration owner is UserDefault.",
                datetime(2026, 1, 1, tzinfo=UTC),
            ).model_copy(update={"user_id": "user:one"})
        ]
    )
    service.evolve_records(
        [
            _record(
                "tx:task",
                "Atlas migration owner is Incident.",
                datetime(2026, 1, 2, tzinfo=UTC),
            ).model_copy(
                update={
                    "task_id": "task:incident",
                    "session_id": "session:incident",
                    "user_id": "user:one",
                }
            )
        ]
    )

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas migration?",
            scope=MemoryScope(
                task_id="task:incident",
                session_id="session:incident",
                user_id="user:one",
            ),
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    assert [states[claim_id].object_value for claim_id in decision.selected_record_ids] == ["Incident"]
    assert any(states[claim_id].object_value == "UserDefault" for claim_id in decision.context_record_ids)


def test_scope_shadowing_is_local_to_each_semantic_claim_during_graph_audit() -> None:
    class _CurrentGraphAnalyzer:
        def analyze(self, **_kwargs: object) -> QueryAnalysis:
            return QueryAnalysis(
                temporal_frame=QueryTemporalFrame(temporal_kind=QueryTemporalKind.CURRENT),
                analysis_source="structured_model",
            )

    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane, query_analyzer=_CurrentGraphAnalyzer())
    service.evolve_records(
        [_record("tx:global", "Atlas project owner is GlobalOwner.", datetime(2026, 1, 1, tzinfo=UTC))]
    )
    service.evolve_records(
        [
            _record(
                "tx:task",
                "Beacon service owner is TaskOwner.",
                datetime(2026, 1, 2, tzinfo=UTC),
            ).model_copy(update={"task_id": "task:incident"})
        ]
    )

    decision = service.retrieve(
        GraphAuditRequest(
            query="Reconstruct the ownership graph.",
            scope=MemoryScope(task_id="task:incident"),
            purpose="graph_audit",
            scope_mode="full",
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    selected_values = {states[claim_id].object_value for claim_id in decision.selected_record_ids}
    assert {"GlobalOwner", "TaskOwner"}.issubset(selected_values)


def test_scope_shadowing_does_not_hide_distinct_same_name_entity() -> None:
    captured_entity_ids: set[str] = set()

    class _CapturingAnalyzer:
        def analyze(self, **kwargs: object) -> QueryAnalysis:
            candidates = kwargs["entity_candidates"]
            assert isinstance(candidates, list)
            captured_entity_ids.update(candidate.entity_id for candidate in candidates)
            return QueryAnalysis(
                temporal_frame=QueryTemporalFrame(
                    temporal_kind=QueryTemporalKind.CURRENT,
                    resolved_entity_ids=["entity:global-project"],
                    resolution_confidence=1.0,
                ),
                analysis_source="structured_model",
            )

    links = [
        EntityLinkState(
            link_id="link:global-project",
            mention_text="Atlas",
            canonical_entity_id="entity:global-project",
            normalized_name="atlas",
            aliases=["Atlas"],
            confidence=1.0,
        ),
        EntityLinkState(
            link_id="link:task-service",
            mention_text="Atlas",
            canonical_entity_id="entity:task-service",
            normalized_name="atlas",
            aliases=["Atlas"],
            confidence=1.0,
            scope=MemoryScope(task_id="task:incident"),
        ),
    ]
    runtime = MemoryEvolutionRetrievalRuntime(
        claim_reader=lambda **_kwargs: [],
        entity_link_reader=lambda: links,
        action_reader=lambda: [],
        query_analyzer=_CapturingAnalyzer(),
        temporal_anchor_catalog=TemporalAnchorCatalog(),
        now_provider=lambda: datetime(2026, 1, 3, tzinfo=UTC),
    )

    runtime.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas project?",
            scope=MemoryScope(task_id="task:incident"),
        )
    )

    assert captured_entity_ids == {"entity:global-project", "entity:task-service"}


def test_heuristic_entity_match_is_context_not_execution_branch_authority() -> None:
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    project = EntityLinkState(
        link_id="link:atlas-project",
        mention_text="Atlas",
        canonical_entity_id="entity:atlas-project",
        normalized_name="atlas",
        aliases=["Atlas"],
        entity_type="project",
        confidence=1.0,
    )
    action = ExtractedAction(
        action_id="action:branch-b-progress",
        action_type="progress",
        target_entity_ids=["entity:branch-b"],
        status="in_progress",
        timestamp=timestamp,
        extraction_run_id="run:branch-b-progress",
    )
    runtime = MemoryEvolutionRetrievalRuntime(
        claim_reader=lambda **_kwargs: [],
        entity_link_reader=lambda: [project],
        action_reader=lambda: [action],
        query_analyzer=EnglishLexicalQueryAnalyzer(),
        temporal_anchor_catalog=TemporalAnchorCatalog(),
        now_provider=lambda: timestamp,
    )

    decision = runtime.retrieve(
        MemoryQueryRequest(
            query="Continue the previous fix for the Atlas project",
            purpose="execution",
            reference_time=timestamp,
        )
    )

    assert decision.query_analysis is not None
    assert decision.query_analysis.analysis_source == "heuristic"
    assert decision.abstained is False
    assert decision.execution_state is not None
    assert decision.execution_state.continuation.branch_id == "entity:branch-b"


def test_execution_context_includes_suppressed_branch_evidence() -> None:
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    actions = [
        ExtractedAction(
            action_id="action:branch-a-blocked",
            action_type="unknown",
            target_entity_ids=["entity:branch-a"],
            status="blocked",
            timestamp=timestamp,
            extraction_run_id="run:branch-a-blocked",
        ),
        ExtractedAction(
            action_id="action:branch-b-progress",
            action_type="progress",
            target_entity_ids=["entity:branch-b"],
            status="in_progress",
            timestamp=timestamp,
            extraction_run_id="run:branch-b-progress",
        ),
    ]
    runtime = MemoryEvolutionRetrievalRuntime(
        claim_reader=lambda **_kwargs: [],
        entity_link_reader=lambda: [],
        action_reader=lambda: actions,
        query_analyzer=EnglishLexicalQueryAnalyzer(),
        temporal_anchor_catalog=TemporalAnchorCatalog(),
        now_provider=lambda: timestamp,
    )

    decision = runtime.retrieve(
        MemoryQueryRequest(
            query="Continue the previous fix",
            purpose="execution",
            reference_time=timestamp,
        )
    )

    assert decision.selected_record_ids == ["branch-b-progress"]
    assert decision.context_record_ids == ["branch-a-blocked"]
    assert decision.execution_state is not None
    assert decision.execution_state.work_state.suppressed_branch_ids == [
        "entity:branch-a"
    ]


def test_scope_shadowing_keeps_readable_global_object_link_referential_integrity() -> None:
    class _OwnerAnalyzer:
        def analyze(self, **_kwargs: object) -> QueryAnalysis:
            return QueryAnalysis(
                predicate_id="owner",
                temporal_frame=QueryTemporalFrame(
                    temporal_kind=QueryTemporalKind.CURRENT,
                    resolved_entity_ids=["entity:owner"],
                    resolution_confidence=1.0,
                ),
                analysis_source="structured_model",
            )

    global_owner = EntityLinkState(
        link_id="link:owner:global",
        mention_text="Iris",
        canonical_entity_id="entity:owner",
        normalized_name="iris",
        aliases=["Iris"],
        confidence=1.0,
    )
    session_owner = global_owner.model_copy(
        update={
            "link_id": "link:owner:session",
            "scope": MemoryScope(
                session_id="session:incident",
                user_id="user:one",
            ),
        }
    )
    state = ClaimState(
        claim_id="claim:service-owner",
        claim_key=ClaimKey(
            subject_entity_id="entity:service",
            predicate_id="owner",
        ),
        object_value="Iris",
        lifecycle_state=ClaimLifecycleState.ACTIVE,
        source_claim_id="source:service-owner",
        confidence=ConfidenceComponents(
            extraction=1.0,
            evidence=1.0,
            source_trust=1.0,
            calibrated=1.0,
        ),
        object_link_id=global_owner.link_id,
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    runtime = MemoryEvolutionRetrievalRuntime(
        claim_reader=lambda **_kwargs: [state],
        entity_link_reader=lambda: [global_owner, session_owner],
        action_reader=lambda: [],
        query_analyzer=_OwnerAnalyzer(),
        temporal_anchor_catalog=TemporalAnchorCatalog(),
        now_provider=lambda: datetime(2026, 1, 3, tzinfo=UTC),
    )

    decision = runtime.retrieve(
        MemoryQueryRequest(
            query="What does Iris own?",
            scope=MemoryScope(
                session_id="session:incident",
                user_id="user:one",
            ),
        )
    )

    assert decision.abstained is False
    assert decision.selected_record_ids == [state.claim_id]


def test_graph_retrieval_applies_scope_and_resolved_entity_constraints() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    service.evolve_records([_record("tx:project", "Atlas migration owner is Bob.", timestamp)])
    service.evolve_records(
        [
            _record("tx:service", "Atlas service owner is Iris.", timestamp).model_copy(
                update={"task_id": "task:incident"}
            )
        ]
    )
    states = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    migration = next(state for state in states if "migration" in state.claim_key.subject_entity_id)

    graph = service.retrieve_current_truth_graph(
        temporal_frame=QueryTemporalFrame(
            temporal_kind=QueryTemporalKind.CURRENT,
            evaluation_time=timestamp,
            scope_kind=QueryScopeKind.TASK,
            scope_key="task:incident",
            resolved_entity_ids=[migration.claim_key.subject_entity_id],
        )
    )

    claim_nodes = [node for node in graph.nodes if node.node_type.value == "claim"]
    assert claim_nodes
    assert all(node.properties.get("scope_key") in {"task:incident", "global"} for node in claim_nodes)
    assert all(
        node.properties.get("subject_entity_id") == migration.claim_key.subject_entity_id for node in claim_nodes
    )


def test_graph_audit_does_not_infer_answer_predicate_and_keeps_definition_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    service.evolve_records([_record("tx:definition", "Atlas project is a project.", timestamp)])
    service.evolve_records([_record("tx:owner", "Atlas project owner is Bob.", timestamp)])

    decision = service.retrieve(
        GraphAuditRequest(
            query="Reconstruct the Atlas project and ownership graph.",
            reference_time=timestamp,
            purpose="graph_audit",
            scope_mode="full",
        )
    )

    assert decision.abstained is False
    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    selected_predicates = {states[claim_id].claim_key.predicate_id for claim_id in decision.selected_record_ids}
    assert "owner" in selected_predicates
    assert "entity_type" in selected_predicates


def test_invalidated_claim_is_not_eligible_for_historical_answer() -> None:
    january = datetime(2026, 1, 1, tzinfo=UTC)
    plane = MemoryPlaneService()
    invalidated = ClaimState(
        claim_id="claim:invalidated",
        claim_key=ClaimKey(subject_entity_id="ent:atlas", predicate_id="owner"),
        object_value="Mallory",
        lifecycle_state=ClaimLifecycleState.INVALIDATED,
        source_claim_id="claim:invalidated",
        confidence=ConfidenceComponents(
            extraction=0.1,
            evidence=0.0,
            source_trust=0.0,
            calibrated=0.0,
        ),
        valid_from=january,
        valid_to=datetime(2026, 2, 1, tzinfo=UTC),
    )
    plane.upsert_record(
        CanonicalMemoryRecord(
            memory_id="mem:evolution:claim:claim:invalidated",
            domain=MemoryDomain.SEMANTIC,
            text="invalidated historical claim",
            content={"memory_evolution_kind": "claim_state", "claim_state": invalidated.model_dump(mode="json")},
            status=CommitStatus.COMMITTED,
            source_kind="memory_evolution",
            timestamp=january,
        )
    )
    service = MemoryEvolutionService(memory_plane=plane)

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owned Atlas in January?",
            reference_time=datetime(2026, 3, 1, tzinfo=UTC),
        )
    )

    assert "claim:invalidated" not in decision.selected_record_ids
    assert decision.abstained is True


def test_structured_query_analysis_constrains_entity_and_predicate_selection() -> None:
    plane = MemoryPlaneService()

    def analyze_structured_query(**kwargs: object) -> dict[str, object]:
        candidates = kwargs["entity_candidates"]
        assert isinstance(candidates, list)
        candidate = next(
            candidate
            for candidate in candidates
            if hasattr(candidate, "names") and any("migration" in name for name in candidate.names)
        )
        subject_entity_id = candidate.entity_id
        return {
            "language": "es",
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": [subject_entity_id],
            "predicate_id": "owner",
            "subject_entity_id": subject_entity_id,
        }

    service = MemoryEvolutionService(
        memory_plane=plane,
        query_analyzer=StructuredQueryAnalyzer(
            analyze_structured_query,
            analyzer_name="test-structured-analyzer",
            analyzer_version="1",
        ),
    )
    service.evolve_records([_record("tx:project", "Atlas migration owner is Bob.", datetime(2026, 1, 1, tzinfo=UTC))])
    service.evolve_records([_record("tx:service", "Atlas service owner is Iris.", datetime(2026, 1, 2, tzinfo=UTC))])
    states = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    project_state = next(state for state in states if "migration" in state.claim_key.subject_entity_id)

    decision = service.retrieve(
        MemoryQueryRequest(
            query="¿Quién es el propietario actual de Atlas?",
            query_language="es",
        )
    )

    assert decision.abstained is False
    assert decision.selected_record_ids
    assert all(candidate.claim_id == project_state.claim_id for candidate in decision.candidates)


@pytest.mark.parametrize(
    ("language", "query"),
    [
        ("en", "Which project is owned by Bob?"),
        ("es", "¿Qué proyecto pertenece a Bob?"),
        ("ja", "Bob が所有するプロジェクトはどれですか？"),
        ("ar", "ما المشروع الذي يملكه بوب؟"),
    ],
)
def test_structured_graph_retrieval_is_language_invariant(
    language: str,
    query: str,
) -> None:
    def analyze_structured_query(**kwargs: object) -> dict[str, object]:
        candidates = kwargs["entity_candidates"]
        assert isinstance(candidates, list)
        project = next(
            candidate
            for candidate in candidates
            if hasattr(candidate, "names") and any("migration" in name.casefold() for name in candidate.names)
        )
        bob = next(
            candidate
            for candidate in candidates
            if hasattr(candidate, "names") and any(name.casefold() == "bob" for name in candidate.names)
        )
        return {
            "language": kwargs["language"],
            "predicate_id": "owner",
            "subject_entity_id": project.entity_id,
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "graph_patterns": [
                {
                    "subject": {
                        "reference_kind": "resolved",
                        "entity_id": project.entity_id,
                    },
                    "predicate_id": "owner",
                    "object": {
                        "entity": {
                            "reference_kind": "resolved",
                            "entity_id": bob.entity_id,
                        },
                        "value_type": "entity",
                    },
                }
            ],
        }

    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        query_analyzer=StructuredQueryAnalyzer(
            analyze_structured_query,
            analyzer_name="test-multilingual-analyzer",
            analyzer_version="1",
        ),
    )
    service.evolve_records(
        [
            _record(
                "tx:project",
                "Atlas migration owner is Bob.",
                datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )

    decision = service.retrieve(MemoryQueryRequest(query=query, query_language=language))

    assert decision.abstained is False
    assert len(decision.selected_record_ids) == 1
    assert decision.query_analysis is not None
    assert decision.query_analysis.analysis_source == "structured_model"
    assert decision.query_analysis.language == language
    assert decision.graph_pattern_resolution is not None
    assert decision.graph_pattern_resolution.status.value == "resolved"
    assert decision.graph_pattern_resolution.resolution_method.value == "structured_constraint"
    assert decision.temporal_frame is not None
    assert decision.temporal_frame.resolution_confidence == 1.0
    assert decision.temporal_frame.resolution_confidence_source == "graph_constraint"


def test_structured_graph_retrieval_abstains_on_ambiguous_object_reference() -> None:
    def analyze_structured_query(**kwargs: object) -> dict[str, object]:
        candidates = kwargs["entity_candidates"]
        assert isinstance(candidates, list)
        project = next(
            candidate
            for candidate in candidates
            if hasattr(candidate, "names") and any("migration" in name.casefold() for name in candidate.names)
        )
        people = [candidate for candidate in candidates if getattr(candidate, "entity_type", None) == "person"]
        assert len(people) >= 2
        return {
            "language": "en",
            "predicate_id": "owner",
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "graph_patterns": [
                {
                    "subject": {
                        "reference_kind": "resolved",
                        "entity_id": project.entity_id,
                    },
                    "predicate_id": "owner",
                    "object": {
                        "entity": {
                            "reference_kind": "ambiguous",
                            "mention": "the owner",
                            "candidate_entity_ids": [
                                people[0].entity_id,
                                people[1].entity_id,
                            ],
                        },
                        "value_type": "entity",
                    },
                }
            ],
        }

    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        query_analyzer=StructuredQueryAnalyzer(
            analyze_structured_query,
            analyzer_name="test-ambiguous-analyzer",
            analyzer_version="1",
        ),
    )
    service.evolve_records(
        [
            _record(
                "tx:project",
                "Atlas migration owner is Bob.",
                datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]
    )
    service.evolve_records(
        [
            _record(
                "tx:service",
                "Atlas service owner is Iris.",
                datetime(2026, 1, 2, tzinfo=UTC),
            )
        ]
    )

    decision = service.retrieve(MemoryQueryRequest(query="Who is the owner?"))

    assert decision.abstained is True
    assert decision.graph_pattern_resolution is not None
    assert decision.graph_pattern_resolution.status.value == "ambiguous"
    assert decision.graph_pattern_resolution.failure_reasons == ["ambiguous_entity_reference"]


def test_natural_query_request_rejects_caller_temporal_override() -> None:
    with pytest.raises(ValueError, match="temporal_frame"):
        MemoryQueryRequest.model_validate(
            {
                "query": "What is the Atlas owner?",
                "reference_time": datetime(2026, 3, 1, tzinfo=UTC),
                "temporal_frame": QueryTemporalFrame(
                    temporal_kind=QueryTemporalKind.HISTORICAL,
                    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                    valid_to=datetime(2026, 2, 1, tzinfo=UTC),
                ),
            }
        )


def test_graph_current_truth_at_time_keeps_point_in_time_truth_without_promoting_it_now() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    january = datetime(2026, 1, 10, tzinfo=UTC)
    march = datetime(2026, 3, 10, tzinfo=UTC)
    service.evolve_records([_record("tx:alice", "Atlas migration owner is Alice.", january)])
    service.evolve_records([_record("tx:bob", "Atlas migration owner is Bob.", march)])

    january_graph = service.retrieve_current_truth_graph(evaluation_time=datetime(2026, 1, 20, tzinfo=UTC))
    current_graph = service.retrieve_current_truth_graph(evaluation_time=datetime(2026, 4, 1, tzinfo=UTC))

    january_labels = {node.label for node in january_graph.nodes if node.node_type.value == "claim"}
    current_labels = {node.label for node in current_graph.nodes if node.node_type.value == "claim"}
    assert any("Alice" in label for label in january_labels)
    assert any("Bob" in label for label in current_labels)
    assert not any("Alice" in label for label in current_labels)


def test_service_named_anchor_is_used_only_after_registration() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    plane.upsert_record(
        _record(
            "event:release",
            "The release week ran from June 1 through June 8.",
            datetime(2026, 6, 4, tzinfo=UTC),
        )
    )
    service.register_temporal_anchor(
        TemporalAnchor(
            anchor_id="anchor:release-week",
            names=["release week"],
            valid_from=datetime(2026, 6, 1, tzinfo=UTC),
            valid_to=datetime(2026, 6, 8, tzinfo=UTC),
            source_ids=["event:release"],
            evidence=[
                {
                    "source_id": "event:release",
                    "span": "release week",
                    "support_type": "explicit_interval",
                }
            ],
        )
    )

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owned Atlas during release week?",
            reference_time=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )

    assert decision.temporal_frame.anchor_id == "anchor:release-week"
    assert decision.temporal_frame.valid_from == datetime(2026, 6, 1, tzinfo=UTC)

    restarted = MemoryEvolutionService(memory_plane=plane)
    restarted_decision = restarted.retrieve(
        MemoryQueryRequest(
            query="Who owned Atlas during release week?",
            reference_time=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )
    assert restarted_decision.temporal_frame.anchor_id == "anchor:release-week"
    assert plane.get_record("mem:evolution:temporal-anchor:anchor:release-week") is not None


def test_production_retrieval_abstains_for_unstructured_non_english_query() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records([_record("tx:project", "Atlas migration owner is Bob.", datetime(2026, 1, 1, tzinfo=UTC))])

    decision = service.retrieve(
        MemoryQueryRequest(
            query="¿Quién es el propietario actual de Atlas?",
            query_language="es",
        )
    )

    assert decision.abstained is True
    assert decision.abstention_reason == "temporal_frame_ambiguous"
    assert decision.query_analysis is not None
    assert decision.query_analysis.analysis_source == "language_guard"


def test_structured_query_provider_failure_is_visible_in_decision_metadata() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_intent": "current",
            "temporal_expression": {"expression_kind": "current"},
            "candidate_entity_ids": ["hidden"],
        },
        analyzer_name="test-provider",
        analyzer_version="1",
    )
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService(), query_analyzer=analyzer)

    decision = service.retrieve(MemoryQueryRequest(query="Who owns Atlas?"))

    assert decision.abstained is True
    assert decision.query_analysis is not None
    assert decision.query_analysis.provider_error == "StructuredQueryConstraintError"
    assert decision.query_analysis.failure_code.value == "constraint_error"
    assert decision.query_analysis.analyzer_name == "test-provider"


def test_service_rejects_temporal_anchor_with_unknown_source() -> None:
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService())
    with pytest.raises(ValueError, match="unknown sources"):
        service.register_temporal_anchor(
            TemporalAnchor(
                anchor_id="anchor:unknown",
                names=["unknown event"],
                valid_from=datetime(2026, 6, 1, tzinfo=UTC),
                valid_to=datetime(2026, 6, 8, tzinfo=UTC),
                source_ids=["missing:event"],
                evidence=[
                    {
                        "source_id": "missing:event",
                        "span": "unknown event",
                        "support_type": "named_event",
                    }
                ],
            )
        )
