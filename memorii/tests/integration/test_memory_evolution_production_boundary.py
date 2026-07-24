from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from memorii.core.llm_config import LLMRuntimeConfig
from memorii.core.llm_provider.fake import FakeLLMStructuredClient
from memorii.core.llm_provider.runner import PromptLLMRunner
from memorii.core.memory_evolution import (
    LLMMemoryExtractor,
    MemoryEvolutionService,
    MemoryExtractionRunError,
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
