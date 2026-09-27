from __future__ import annotations

from datetime import UTC, datetime

import pytest
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore
from memorii.core.semantic_ingestion.catalog_authority import CatalogAuthorityScope
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservation,
    CoverageObservationRepository,
    CoverageSemanticOutcome,
    DiscoveryProcessingState,
    ObserverBindingIdentity,
    new_coverage_observation,
)


def _observation(*, binding: ObserverBindingIdentity | None = None) -> CoverageObservation:
    return new_coverage_observation(
        source_id="semantic_ingestion:source:one",
        source_digest="1" * 64,
        source_span=None,
        source_scope_digest="2" * 64,
        origin_lineage_digest="3" * 64,
        session_id="session:one",
        principal_id="user:one",
        agent_id="agent:one",
        observed_at=datetime(2026, 9, 27, tzinfo=UTC),
        catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
        catalog_digest="4" * 64,
        observer_binding=binding,
    )


def test_no_capability_observation_is_durable_inert_and_idempotent() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = CoverageObservationRepository(plane)
    observation = _observation()

    assert observation.processing_state == DiscoveryProcessingState.PENDING_NO_CAPABILITY
    assert observation.semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    assert repository.create(observation) == observation
    assert repository.create(observation) == observation
    assert repository.load(observation.observation_id) == observation
    records = plane.list_records()
    assert len(records) == 1
    assert not [record for record in records if record.domain.value in {"semantic", "user"}]


def test_authorized_binding_starts_queued_under_a_distinct_identity() -> None:
    binding = ObserverBindingIdentity(
        binding_version="observer:v1",
        provider="local",
        model="test-model",
        prompt_version="prompt:v1",
        transport="in_process",
        egress_policy_digest="5" * 64,
        output_schema_digest="6" * 64,
    )
    pending = _observation()
    queued = _observation(binding=binding)

    assert queued.processing_state == DiscoveryProcessingState.QUEUED
    assert queued.semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    assert queued.observation_id != pending.observation_id


def test_unclassified_state_cannot_claim_a_verified_gap() -> None:
    pending = _observation()
    payload = pending.model_dump(mode="python")
    payload["semantic_outcome"] = CoverageSemanticOutcome.UNSUPPORTED_RELATION

    with pytest.raises(ValueError, match="unclassified observation"):
        CoverageObservation.model_validate(payload)


def test_unknown_or_tampered_persisted_observation_fails_closed() -> None:
    observation = _observation()
    payload = observation.model_dump(mode="python")
    payload["catalog_digest"] = "9" * 64

    with pytest.raises(ValueError, match="digest mismatch"):
        CoverageObservation.model_validate(payload)
