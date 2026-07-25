from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from memorii.core.benchmark.memory_evolution_runtime.extractors import (
    RecordedExtractionRun,
    RecordingMemoryExtractor,
)
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import (
    LLMMemoryExtractor,
    MemoryEvolutionService,
    MemoryExtractionRunError,
    MemoryGraphEdgeType,
    MemoryGraphNodeType,
    MemoryQueryRequest,
    MemoryScope,
    RetrievalView,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.domain.enums import CommitStatus, MemoryDomain


class _QueuedStructuredClient(FakeLLMStructuredClient):
    def __init__(self, responses: list[dict[str, object]]) -> None:
        super().__init__(default_response="{}")
        self._responses = [json.dumps(response) for response in responses]

    def complete_structured(self, request, *, config):
        if not self._responses:
            raise AssertionError("unexpected extraction call")
        self._default_response = self._responses.pop(0)
        return super().complete_structured(request, config=config)


def _record(memory_id: str, text: str, timestamp: datetime) -> CanonicalMemoryRecord:
    return CanonicalMemoryRecord(
        memory_id=memory_id,
        domain=MemoryDomain.TRANSCRIPT,
        text=text,
        content={"text": text},
        status=CommitStatus.COMMITTED,
        source_kind="user",
        timestamp=timestamp,
        task_id="task:atlas",
        is_raw_event=True,
    )


def _owner_response(
    *,
    source_id: str,
    project_name: str,
    owner: str,
    quote: str,
    confidence: float,
) -> dict[str, object]:
    return {
        "entities": [
            {
                "entity_ref": "project",
                "mention_text": project_name,
                "aliases": ["Atlas", "Atlas Billing Migration"],
                "entity_type": "project",
                "source_id": source_id,
                "quote": project_name,
                "confidence": confidence,
            },
            {
                "entity_ref": "owner",
                "mention_text": owner,
                "aliases": [owner],
                "entity_type": "person",
                "source_id": source_id,
                "quote": owner,
                "confidence": confidence,
            },
        ],
        "claims": [
            {
                "subject_entity_ref": "project",
                "predicate_id": "owner",
                "object_value": owner,
                "object_entity_ref": "owner",
                "source_id": source_id,
                "quote": quote,
                "confidence": confidence,
            }
        ],
        "actions": [],
    }


@pytest.mark.integration
def test_model_shaped_ingestion_trace_replays_proposal_and_graph_delta() -> None:
    timestamp = datetime(2026, 1, 10, tzinfo=UTC)
    delegate = LLMMemoryExtractor(
        runner=PromptLLMRunner(
            client=_QueuedStructuredClient(
                [
                    _owner_response(
                        source_id="tx:trace",
                        project_name="Atlas Billing Migration",
                        owner="Alice",
                        quote="Atlas Billing Migration owner is Alice",
                        confidence=0.9,
                    ),
                    _owner_response(
                        source_id="tx:trace-2",
                        project_name="Atlas",
                        owner="Bob",
                        quote="Bob owns Atlas",
                        confidence=0.9,
                    ),
                ]
            ),
            config=LLMRuntimeConfig(provider="none"),
        )
    )
    extractor = RecordingMemoryExtractor(delegate=delegate)
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=extractor,
    )

    result = service.evolve_records(
        [
            _record(
                "tx:trace",
                "Atlas Billing Migration owner is Alice.",
                timestamp,
            )
        ]
    )
    extractor.record_evolution_results([result])
    second_result = service.evolve_records(
        [
            _record(
                "tx:trace-2",
                "Bob owns Atlas. Atlas means Atlas Billing Migration.",
                timestamp,
            )
        ]
    )
    extractor.record_evolution_results([second_result])
    replayed_traces = [
        RecordedExtractionRun.model_validate_json(trace.model_dump_json())
        for trace in extractor.recorded_runs
    ]
    replayed = replayed_traces[0]

    assert replayed.structured_proposal is not None
    assert replayed.structured_proposal.entities[0].entity_ref == "project"
    assert replayed.input_observations[0].source_id == "tx:trace"
    assert replayed.input_observations[0].modality == "assertion"
    assert replayed.graph_delta.added_nodes
    assert replayed.graph_delta.added_edges
    assert replayed.graph_delta.removed_node_ids == []
    assert replayed.graph_delta.removed_edge_ids == []
    replayed_nodes: dict[str, object] = {}
    replayed_edges: dict[str, object] = {}
    for trace in replayed_traces:
        _apply_trace_delta(replayed_nodes, replayed_edges, trace)
    assert replayed_nodes == {
        node.node_id: node
        for node in replayed_traces[-1].graph_nodes
    }
    assert replayed_edges == {
        edge.edge_id: edge
        for edge in replayed_traces[-1].graph_edges
    }


@pytest.mark.integration
def test_fake_provider_ingestion_to_retrieval_matches_independent_expected_graph() -> None:
    january = datetime(2026, 1, 10, tzinfo=UTC)
    march = datetime(2026, 3, 10, tzinfo=UTC)
    client = _QueuedStructuredClient(
        [
            _owner_response(
                source_id="tx:alice",
                project_name="Atlas Billing Migration",
                owner="Alice",
                quote="Atlas Billing Migration owner is Alice",
                confidence=0.99,
            ),
            _owner_response(
                source_id="tx:bob",
                project_name="Atlas",
                owner="Bob",
                quote="Bob owns Atlas",
                confidence=0.01,
            ),
        ]
    )
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=LLMMemoryExtractor(
            runner=PromptLLMRunner(
                client=client,
                config=LLMRuntimeConfig(provider="none"),
            )
        ),
    )

    service.evolve_records([_record("tx:alice", "Atlas Billing Migration owner is Alice.", january)])
    first_prefix_states = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    assert [
        (state.object_value, state.lifecycle_state.value)
        for state in first_prefix_states
    ] == [("Alice", "active")]

    service.evolve_records([_record("tx:bob", "Bob owns Atlas. Atlas means Atlas Billing Migration.", march)])
    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owns the Atlas Billing Migration now?",
            reference_time=datetime(2026, 3, 20, tzinfo=UTC),
            scope=MemoryScope(task_id="task:atlas"),
            include_conflicts=True,
        )
    )

    states = {state.claim_id: state for state in service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)}
    observable = {
        "selected_owner": [states[claim_id].object_value for claim_id in decision.selected_record_ids],
        "rejected_owners": sorted(states[claim_id].object_value for claim_id in decision.rejected_record_ids),
        "lifecycle_by_owner": {state.object_value: state.lifecycle_state.value for state in states.values()},
    }
    expected = {
        "selected_owner": ["Bob"],
        "rejected_owners": ["Alice"],
        "lifecycle_by_owner": {"Alice": "superseded", "Bob": "active"},
    }

    assert observable == expected


@pytest.mark.integration
def test_model_shaped_ingestion_matches_hand_authored_graph_after_each_prefix() -> None:
    january = datetime(2026, 1, 10, tzinfo=UTC)
    march = datetime(2026, 3, 10, tzinfo=UTC)
    client = _QueuedStructuredClient(
        [
            _owner_response(
                source_id="tx:alice",
                project_name="Atlas Billing Migration",
                owner="Alice",
                quote="Atlas Billing Migration owner is Alice",
                confidence=0.99,
            ),
            _owner_response(
                source_id="tx:bob",
                project_name="Atlas",
                owner="Bob",
                quote="Bob owns Atlas",
                confidence=0.9,
            ),
        ]
    )
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=LLMMemoryExtractor(
            runner=PromptLLMRunner(
                client=client,
                config=LLMRuntimeConfig(provider="none"),
            )
        ),
    )

    service.evolve_records(
        [_record("tx:alice", "Atlas Billing Migration owner is Alice.", january)]
    )

    assert _persisted_owner_graph_shape(service) == {
        "entities": [
            (
                ("alice",),
                "person",
                "active",
                "task:atlas",
                ("tx:alice",),
            ),
            (
                ("atlas", "atlas billing migration"),
                "project",
                "active",
                "task:atlas",
                ("tx:alice",),
            ),
        ],
        "claims": [
            (
                ("atlas", "atlas billing migration"),
                "owner",
                ("alice",),
                "active",
                "task:atlas",
                ("tx:alice",),
            )
        ],
        "lineage": [],
    }

    service.evolve_records(
        [_record("tx:bob", "Bob owns Atlas. Atlas means Atlas Billing Migration.", march)]
    )

    assert _persisted_owner_graph_shape(service) == {
        "entities": [
            (
                ("alice",),
                "person",
                "active",
                "task:atlas",
                ("tx:alice",),
            ),
            (
                ("atlas", "atlas billing migration"),
                "project",
                "active",
                "task:atlas",
                ("tx:alice", "tx:bob"),
            ),
            (
                ("bob",),
                "person",
                "active",
                "task:atlas",
                ("tx:bob",),
            ),
        ],
        "claims": [
            (
                ("atlas", "atlas billing migration"),
                "owner",
                ("alice",),
                "superseded",
                "task:atlas",
                ("tx:alice",),
            ),
            (
                ("atlas", "atlas billing migration"),
                "owner",
                ("bob",),
                "active",
                "task:atlas",
                ("tx:bob",),
            ),
        ],
        "lineage": [
            (("alice",), "conflicts_with", ("bob",)),
            (("bob",), "conflicts_with", ("alice",)),
            (("bob",), "supersedes", ("alice",)),
        ],
    }


@pytest.mark.integration
def test_fake_provider_declared_owner_ref_canonicalizes_value_before_commit() -> None:
    timestamp = datetime(2026, 1, 10, tzinfo=UTC)
    client = _QueuedStructuredClient(
        [
            {
                "entities": [
                    {
                        "entity_ref": "project",
                        "mention_text": "Atlas",
                        "aliases": ["Atlas"],
                        "entity_type": "project",
                        "source_id": "tx:grounded-owner",
                        "quote": "Atlas",
                        "confidence": 0.9,
                    },
                    {
                        "entity_ref": "owner",
                        "mention_text": "Alice",
                        "aliases": ["Alice"],
                        "entity_type": "person",
                        "source_id": "tx:grounded-owner",
                        "quote": "Alice",
                        "confidence": 0.9,
                    },
                ],
                "claims": [
                    {
                        "subject_entity_ref": "project",
                        "predicate_id": "owner",
                        "object_value": "",
                        "object_entity_ref": "owner",
                        "source_id": "tx:grounded-owner",
                        "quote": "Atlas owner is Alice",
                        "confidence": 0.9,
                    }
                ],
                "actions": [],
            }
        ]
    )
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=LLMMemoryExtractor(
            runner=PromptLLMRunner(
                client=client,
                config=LLMRuntimeConfig(provider="none"),
            )
        ),
    )

    service.evolve_records([_record("tx:grounded-owner", "Atlas owner is Alice.", timestamp)])

    states = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)
    assert len(states) == 1
    assert states[0].object_value == "Alice"
    assert states[0].object_link_id is not None


@pytest.mark.integration
def test_fake_provider_invalid_typed_claim_fails_before_state_mutation() -> None:
    timestamp = datetime(2026, 1, 10, tzinfo=UTC)
    client = _QueuedStructuredClient(
        [
            {
                "entities": [
                    {
                        "entity_ref": "project",
                        "mention_text": "Atlas",
                        "aliases": ["Atlas"],
                        "entity_type": "project",
                        "source_id": "tx:invalid-owner",
                        "quote": "Atlas",
                        "confidence": 0.9,
                    }
                ],
                "claims": [
                    {
                        "subject_entity_ref": "project",
                        "predicate_id": "owner",
                        "object_value": "Charlie",
                        "object_entity_ref": None,
                        "source_id": "tx:invalid-owner",
                        "quote": "Atlas owner is Alice",
                        "confidence": 0.9,
                    }
                ],
                "actions": [],
            }
        ]
    )
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=LLMMemoryExtractor(
            runner=PromptLLMRunner(
                client=client,
                config=LLMRuntimeConfig(provider="none"),
            )
        ),
    )

    with pytest.raises(
        MemoryExtractionRunError,
        match="memory extraction is not commit-eligible: partial:output_validation",
    ):
        service.evolve_records([_record("tx:invalid-owner", "Atlas owner is Alice.", timestamp)])

    assert service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS) == []


@pytest.mark.integration
@pytest.mark.parametrize(
    ("source_id", "text", "invalid_response"),
    [
        (
            "tx:misbound-type",
            "Alice said Beacon is a project.",
            {
                "entities": [
                    {
                        "entity_ref": "alice",
                        "mention_text": "Alice",
                        "aliases": [],
                        "entity_type": "unknown",
                        "source_id": "tx:misbound-type",
                        "quote": "Alice",
                        "confidence": 0.9,
                    },
                    {
                        "entity_ref": "beacon",
                        "mention_text": "Beacon",
                        "aliases": [],
                        "entity_type": "unknown",
                        "source_id": "tx:misbound-type",
                        "quote": "Beacon",
                        "confidence": 0.9,
                    },
                ],
                "claims": [
                    {
                        "subject_entity_ref": "alice",
                        "predicate_id": "entity_type",
                        "object_value": "project",
                        "object_entity_ref": None,
                        "source_id": "tx:misbound-type",
                        "quote": "Alice said Beacon is a project",
                        "confidence": 0.9,
                    }
                ],
                "actions": [],
            },
        ),
        (
            "tx:misbound-owner",
            "Carol owns Beacon, not Comet.",
            {
                "entities": [
                    {
                        "entity_ref": "carol",
                        "mention_text": "Carol",
                        "aliases": [],
                        "entity_type": "person",
                        "source_id": "tx:misbound-owner",
                        "quote": "Carol",
                        "confidence": 0.9,
                    },
                    {
                        "entity_ref": "beacon",
                        "mention_text": "Beacon",
                        "aliases": [],
                        "entity_type": "project",
                        "source_id": "tx:misbound-owner",
                        "quote": "Beacon",
                        "confidence": 0.9,
                    },
                    {
                        "entity_ref": "comet",
                        "mention_text": "Comet",
                        "aliases": [],
                        "entity_type": "project",
                        "source_id": "tx:misbound-owner",
                        "quote": "Comet",
                        "confidence": 0.9,
                    },
                ],
                "claims": [
                    {
                        "subject_entity_ref": "comet",
                        "predicate_id": "owner",
                        "object_value": "Carol",
                        "object_entity_ref": "carol",
                        "source_id": "tx:misbound-owner",
                        "quote": "Carol owns Beacon, not Comet",
                        "confidence": 0.9,
                    }
                ],
                "actions": [],
            },
        ),
    ],
)
def test_semantically_misbound_proposal_is_atomic_at_service_boundary(
    source_id: str,
    text: str,
    invalid_response: dict[str, object],
) -> None:
    timestamp = datetime(2026, 1, 10, tzinfo=UTC)
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=LLMMemoryExtractor(
            runner=PromptLLMRunner(
                client=_QueuedStructuredClient(
                    [
                        _owner_response(
                            source_id="tx:baseline-owner",
                            project_name="Atlas",
                            owner="Alice",
                            quote="Atlas owner is Alice",
                            confidence=0.9,
                        ),
                        invalid_response,
                    ]
                ),
                config=LLMRuntimeConfig(provider="none"),
            )
        ),
    )
    service.evolve_records(
        [_record("tx:baseline-owner", "Atlas owner is Alice.", timestamp)]
    )
    before = service.retrieve_graph_snapshot().model_dump(
        mode="json",
        exclude={"generated_at"},
    )

    with pytest.raises(MemoryExtractionRunError) as error:
        service.evolve_records([_record(source_id, text, timestamp)])

    assert error.value.run.failure_code is not None
    assert error.value.run.failure_code.value == "output_validation"
    assert error.value.run.status.value == "partial"
    assert service.retrieve_graph_snapshot().model_dump(
        mode="json",
        exclude={"generated_at"},
    ) == before


@pytest.mark.integration
def test_generic_semantic_fact_cannot_satisfy_typed_owner_retrieval() -> None:
    timestamp = datetime(2026, 1, 10, tzinfo=UTC)
    client = _QueuedStructuredClient(
        [
            {
                "entities": [
                    {
                        "entity_ref": "project",
                        "mention_text": "Atlas",
                        "aliases": ["Atlas"],
                        "entity_type": "project",
                        "source_id": "tx:semantic-owner",
                        "quote": "Atlas",
                        "confidence": 0.9,
                    },
                    {
                        "entity_ref": "alice",
                        "mention_text": "Alice",
                        "aliases": ["Alice"],
                        "entity_type": "person",
                        "source_id": "tx:semantic-owner",
                        "quote": "Alice",
                        "confidence": 0.9,
                    },
                ],
                "claims": [
                    {
                        "subject_entity_ref": "project",
                        "predicate_id": "semantic_fact",
                        "object_value": "Alice",
                        "object_entity_ref": "alice",
                        "source_id": "tx:semantic-owner",
                        "quote": "Atlas is associated with Alice",
                        "confidence": 0.9,
                    }
                ],
                "actions": [],
            }
        ]
    )
    service = MemoryEvolutionService(
        memory_plane=MemoryPlaneService(),
        extractor=LLMMemoryExtractor(
            runner=PromptLLMRunner(
                client=client,
                config=LLMRuntimeConfig(provider="none"),
            )
        ),
    )

    service.evolve_records([_record("tx:semantic-owner", "Atlas is associated with Alice.", timestamp)])
    decision = service.retrieve(
        MemoryQueryRequest(
            query="Who owns Atlas?",
            reference_time=datetime(2026, 1, 20, tzinfo=UTC),
            scope=MemoryScope(task_id="task:atlas"),
        )
    )
    states = service.retrieve_claim_states(view=RetrievalView.ALL_VERSIONS)

    assert [(state.claim_key.predicate_id, state.object_value) for state in states] == [("semantic_fact", "Alice")]
    assert decision.selected_record_ids == []


def _persisted_owner_graph_shape(
    service: MemoryEvolutionService,
) -> dict[str, list[tuple[object, ...]]]:
    snapshot = service.retrieve_graph_snapshot()
    outgoing: dict[str, list[tuple[MemoryGraphEdgeType, str]]] = {}
    for edge in snapshot.edges:
        outgoing.setdefault(edge.source_node_id, []).append(
            (edge.edge_type, edge.target_node_id)
        )

    entity_aliases: dict[str, tuple[str, ...]] = {}
    entities: list[tuple[object, ...]] = []
    for node in snapshot.nodes:
        if (
            node.node_type != MemoryGraphNodeType.ENTITY
            or node.lifecycle_state == "candidate"
        ):
            continue
        aliases = tuple(
            sorted(
                {
                    alias.strip().casefold()
                    for alias in node.properties.get("aliases", "").split("|")
                    if alias.strip()
                }
            )
        )
        entity_aliases[node.node_id] = aliases
        entities.append(
            (
                aliases,
                node.properties.get("entity_type", ""),
                node.lifecycle_state.value,
                node.properties.get("scope_key", ""),
                tuple(sorted(node.source_record_ids)),
            )
        )

    claims: list[tuple[object, ...]] = []
    claim_objects: dict[str, tuple[str, ...]] = {}
    for node in snapshot.nodes:
        if node.node_type != MemoryGraphNodeType.CLAIM:
            continue
        subject_id = next(
            target_id
            for edge_type, target_id in outgoing.get(node.node_id, [])
            if edge_type == MemoryGraphEdgeType.HAS_SUBJECT
        )
        object_id = next(
            target_id
            for edge_type, target_id in outgoing.get(node.node_id, [])
            if edge_type == MemoryGraphEdgeType.HAS_OBJECT
        )
        claim_objects[node.node_id] = entity_aliases[object_id]
        claims.append(
            (
                entity_aliases[subject_id],
                node.properties.get("predicate_id", ""),
                entity_aliases[object_id],
                node.lifecycle_state.value,
                node.properties.get("scope_key", ""),
                tuple(sorted(node.source_record_ids)),
            )
        )
    lineage = sorted(
        (
            claim_objects[edge.source_node_id],
            edge.edge_type.value,
            claim_objects[edge.target_node_id],
        )
        for edge in snapshot.edges
        if edge.edge_type
        in {
            MemoryGraphEdgeType.SUPERSEDES,
            MemoryGraphEdgeType.CONFLICTS_WITH,
            MemoryGraphEdgeType.REKEYED_FROM,
        }
        and edge.source_node_id in claim_objects
        and edge.target_node_id in claim_objects
    )
    return {
        "entities": sorted(entities),
        "claims": sorted(claims),
        "lineage": lineage,
    }


def _apply_trace_delta(
    nodes: dict[str, object],
    edges: dict[str, object],
    trace: RecordedExtractionRun,
) -> None:
    for node_id in trace.graph_delta.removed_node_ids:
        nodes.pop(node_id)
    for node in [*trace.graph_delta.added_nodes, *trace.graph_delta.updated_nodes]:
        nodes[node.node_id] = node
    for edge_id in trace.graph_delta.removed_edge_ids:
        edges.pop(edge_id)
    for edge in [*trace.graph_delta.added_edges, *trace.graph_delta.updated_edges]:
        edges[edge.edge_id] = edge
