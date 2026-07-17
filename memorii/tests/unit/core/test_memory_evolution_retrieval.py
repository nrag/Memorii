from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution import GraphAuditRequest, MemoryEvolutionService, MemoryQueryRequest
from memorii.core.memory_evolution.graph import MemoryGraphStore
from memorii.core.memory_evolution.models import (
    ClaimKey,
    ClaimLifecycleState,
    ClaimState,
    ConfidenceComponents,
    RetrievalView,
)
from memorii.core.memory_evolution.temporal import (
    QueryAnalysis,
    QueryScopeKind,
    QueryTemporalFrame,
    QueryTemporalKind,
    StructuredQueryAnalyzer,
    TemporalAnchor,
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
            include_conflicts=True,
        )
    )
    historical = service.retrieve(
        MemoryQueryRequest(
            query="Who owned the Atlas migration in January?",
            reference_time=datetime(2026, 3, 20, tzinfo=UTC),
            include_conflicts=True,
        )
    )

    assert current.selected_record_ids
    assert historical.selected_record_ids
    assert current.selected_record_ids != historical.selected_record_ids
    assert set(current.rejected_record_ids)
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


def test_request_scope_mismatch_with_supplied_frame_abstains() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records([_record("tx:scope", "Atlas owner is Bob.", datetime(2026, 1, 1, tzinfo=UTC))])

    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owns Atlas?",
            scope_key="task:one",
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.CURRENT,
                scope_kind=QueryScopeKind.TASK,
                scope_key="task:two",
                evaluation_time=datetime(2026, 1, 2, tzinfo=UTC),
            ),
        )
    )

    assert decision.abstained is True
    assert decision.resolution_status == "ambiguous"


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


def test_scoped_retrieval_prefers_exact_scope_over_global_fallback() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    service.evolve_records(
        [_record("tx:global", "Atlas migration owner is Global.", datetime(2026, 1, 1, tzinfo=UTC))]
    )
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
            scope_key="task:incident",
            task_id="task:incident",
            reference_time=datetime(2026, 1, 3, tzinfo=UTC),
        )
    )

    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    assert decision.selected_record_ids
    assert states[decision.selected_record_ids[0]].object_value == "Incident"
    assert all(states[claim_id].object_value != "Global" for claim_id in decision.selected_record_ids)


def test_graph_retrieval_applies_scope_and_resolved_entity_constraints() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    service.evolve_records([_record("tx:project", "Atlas migration owner is Bob.", timestamp)])
    service.evolve_records(
        [_record("tx:service", "Atlas service owner is Iris.", timestamp).model_copy(update={"task_id": "task:incident"})]
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
        node.properties.get("subject_entity_id") == migration.claim_key.subject_entity_id
        for node in claim_nodes
    )


def test_graph_audit_does_not_infer_answer_predicate_and_keeps_definition_claims() -> None:
    plane = MemoryPlaneService()
    service = MemoryEvolutionService(memory_plane=plane)
    timestamp = datetime(2026, 1, 3, tzinfo=UTC)
    service.evolve_records([_record("tx:definition", "Atlas is a project.", timestamp)])
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
            "temporal_frame": {
                "temporal_kind": "current",
                "resolved_entity_ids": [subject_entity_id],
            },
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
            query_analysis=QueryAnalysis(
                language="es",
                temporal_frame=QueryTemporalFrame(
                    temporal_kind=QueryTemporalKind.CURRENT,
                    resolved_entity_ids=[project_state.claim_key.subject_entity_id],
                ),
                predicate_id=project_state.claim_key.predicate_id,
                subject_entity_id=project_state.claim_key.subject_entity_id,
                analysis_source="structured_model",
            ),
        )
    )

    assert decision.abstained is False
    assert decision.selected_record_ids
    assert all(candidate.claim_id == project_state.claim_id for candidate in decision.candidates)


def test_caller_temporal_frame_cannot_bypass_configured_query_analyzer() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {
            "temporal_frame": {"temporal_kind": "current"},
        },
        analyzer_name="test-authoritative-analyzer",
        analyzer_version="1",
    )
    service = MemoryEvolutionService(memory_plane=MemoryPlaneService(), query_analyzer=analyzer)

    decision = service.retrieve(
        MemoryQueryRequest(
            query="What is the Atlas owner?",
            reference_time=datetime(2026, 3, 1, tzinfo=UTC),
            temporal_frame=QueryTemporalFrame(
                temporal_kind=QueryTemporalKind.HISTORICAL,
                valid_from=datetime(2026, 1, 1, tzinfo=UTC),
                valid_to=datetime(2026, 2, 1, tzinfo=UTC),
            ),
        )
    )

    assert decision.abstained is True
    assert decision.resolution_status == "ambiguous"
    assert decision.abstention_reason is not None
    assert "caller temporal context" in decision.abstention_reason


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


def test_structured_query_provider_failure_is_visible_in_decision_metadata() -> None:
    analyzer = StructuredQueryAnalyzer(
        lambda **_kwargs: {"temporal_frame": {"temporal_kind": "current", "resolved_entity_ids": ["hidden"]}},
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
