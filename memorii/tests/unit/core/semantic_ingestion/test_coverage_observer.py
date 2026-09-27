from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import InMemoryMemoryPlaneStore, JsonlMemoryPlaneStore
from memorii.core.semantic_ingestion.catalog_authority import (
    CatalogAuthorityScope,
    CatalogVersion,
    SelectedCatalogAuthorityRepository,
    ThreePredicateSeedCatalogAuthorityRepository,
)
from memorii.core.semantic_ingestion.coverage_observation import (
    CoverageObservation,
    CoverageObservationRepository,
    CoverageSemanticOutcome,
    CoverageSourceSpan,
    DiscoveryProcessingState,
    ObserverBindingIdentity,
    new_coverage_observation,
    start_coverage_observation,
)
from memorii.core.semantic_ingestion.coverage_observer import (
    CoverageObserverRunner,
    OntologyObservationRequest,
    OntologyObservationResult,
    OntologyObservationResultRepository,
)
from memorii.core.semantic_ingestion.coverage_recurrence import (
    CoverageRecurrenceRepository,
    RelationGapSignature,
    VerifiedCoverageGapRepository,
)
from memorii.core.semantic_ingestion.coverage_validation import CoreCoverageGapValidator

_BINDING = ObserverBindingIdentity(
    binding_version="observer:v1",
    provider="host",
    model="host-model",
    prompt_version="ontology-observe:v1",
    transport="host_callback",
    egress_policy_digest="5" * 64,
    output_schema_digest="6" * 64,
)
_SIGNATURE = RelationGapSignature.create(
    normalized_relation_meaning="mentors",
    subject_type_id="Person",
    object_type_id="Person",
    domain_id="organization",
    evidence_rule_id="direct_assertion:v1",
)
_CATALOG_VERSION_DIGEST = CatalogVersion.genesis(
    catalog_digest=ThreePredicateSeedCatalogAuthorityRepository().resolve_base().catalog_digest
).version_digest


@dataclass
class _Observer:
    result: object
    binding: ObserverBindingIdentity = _BINDING

    def observe(self, request: OntologyObservationRequest) -> object:
        assert request.source_text == "Alice mentors Bob."
        return self.result


class _UnavailableObserver:
    binding = _BINDING

    def observe(self, request: OntologyObservationRequest) -> object:
        raise OSError(request.observation_id)


def _observation(
    ordinal: int,
    *,
    lineage: str,
    session_id: str,
    catalog_digest: str = _CATALOG_VERSION_DIGEST,
) -> CoverageObservation:
    return new_coverage_observation(
        source_id=f"semantic_ingestion:source:{ordinal}",
        source_digest=f"{ordinal:x}" * 64,
        source_span=None,
        source_scope_digest="2" * 64,
        origin_lineage_digest=lineage,
        session_id=session_id,
        principal_id="user:one",
        agent_id="agent:one",
        observed_at=datetime(2026, 9, 27, tzinfo=UTC)
        + timedelta(minutes=ordinal),
        catalog_scope=CatalogAuthorityScope(schema_version=1, kind="base"),
        catalog_digest=catalog_digest,
        observer_binding=_BINDING,
    )


def _runner(
    plane: MemoryPlaneService, result: object
) -> CoverageObserverRunner:
    SelectedCatalogAuthorityRepository(
        plane,
        SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest()),
    ).ensure_seed_genesis()
    return CoverageObserverRunner(
        observation_repository=CoverageObservationRepository(plane),
        gap_repository=VerifiedCoverageGapRepository(plane),
        recurrence_repository=CoverageRecurrenceRepository(plane),
        result_repository=OntologyObservationResultRepository(plane),
        capability=_Observer(result),
        gap_validator=CoreCoverageGapValidator(plane),
    )


def _gap_result(*, span: CoverageSourceSpan | None = None) -> OntologyObservationResult:
    exact = span or CoverageSourceSpan(start=0, end=17)
    return OntologyObservationResult.create(
        semantic_outcome=CoverageSemanticOutcome.UNSUPPORTED_RELATION,
        source_span=exact,
        source_quote="Alice mentors Bob" if exact.end == 17 else "wrong",
        signature=_SIGNATURE,
    )


def test_authorized_observer_updates_recurrence_at_exact_threshold() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = CoverageObservationRepository(plane)
    runner = _runner(plane, _gap_result())
    results = []
    for observation in (
        _observation(1, lineage="a" * 64, session_id="session:one"),
        _observation(2, lineage="b" * 64, session_id="session:one"),
        _observation(3, lineage="c" * 64, session_id="session:two"),
    ):
        repository.create(observation)
        results.append(
            runner.run(observation=observation, source_text="Alice mentors Bob.")
        )

    assert [item.recurrence_group.proposal_eligible for item in results] == [
        False,
        False,
        True,
    ]
    assert results[-1].recurrence_group.independent_lineage_count == 3
    assert results[-1].recurrence_group.distinct_session_count == 2
    assert not [
        record
        for record in plane.list_records()
        if record.domain.value in {"semantic", "user"}
    ]


def test_invalid_span_or_signature_becomes_uncertain_without_gap() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = CoverageObservationRepository(plane)
    observation = _observation(
        1, lineage="a" * 64, session_id="session:one"
    )
    repository.create(observation)

    result = _runner(
        plane,
        _gap_result(span=CoverageSourceSpan(start=0, end=5)),
    ).run(observation=observation, source_text="Alice mentors Bob.")

    assert result.observation.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert result.observation.semantic_outcome == CoverageSemanticOutcome.UNCERTAIN
    assert result.recurrence_group is None
    assert VerifiedCoverageGapRepository(plane).for_group(
        catalog_scope=observation.catalog_scope,
        catalog_digest=observation.catalog_digest,
        source_scope_digest=observation.source_scope_digest,
        signature=_SIGNATURE,
    ) == ()


def test_core_denies_registered_relation_alias_and_admits_unknown_relation() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = SelectedCatalogAuthorityRepository(
        plane,
        SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest()),
    )
    repository.ensure_seed_genesis()
    observation = _observation(1, lineage="a" * 64, session_id="session:one")
    validator = CoreCoverageGapValidator(plane)
    covered_alias = RelationGapSignature.create(
        normalized_relation_meaning="project owner",
        subject_type_id="Project",
        object_type_id="Person",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )

    assert validator.validates(observation=observation, signature=covered_alias) is False
    assert validator.validates(observation=observation, signature=_SIGNATURE) is True


def test_catalog_rotation_uses_observation_pinned_version() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = SelectedCatalogAuthorityRepository(
        plane,
        SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest()),
    )
    repository.ensure_seed_genesis()
    seed_observation = _observation(
        1, lineage="a" * 64, session_id="session:one"
    )
    repository.install_default_catalog_release()
    selected = repository.resolve_selected_bundle()
    default_observation = _observation(
        2,
        lineage="b" * 64,
        session_id="session:two",
        catalog_digest=selected.version.version_digest,
    )
    reports_to = RelationGapSignature.create(
        normalized_relation_meaning="reports to",
        subject_type_id="Person",
        object_type_id="Person",
        domain_id="organization",
        evidence_rule_id="direct_assertion:v1",
    )
    validator = CoreCoverageGapValidator(plane)

    assert validator.validates(observation=seed_observation, signature=reports_to) is True
    assert validator.validates(observation=default_observation, signature=reports_to) is False


def test_provider_outage_retries_after_jsonl_reopen(tmp_path: Path) -> None:
    storage_path = tmp_path / "memory-plane"
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage_path))
    repository = CoverageObservationRepository(plane)
    observation = _observation(
        1, lineage="a" * 64, session_id="session:one"
    )
    repository.create(observation)
    runner = CoverageObserverRunner(
        observation_repository=repository,
        gap_repository=VerifiedCoverageGapRepository(plane),
        recurrence_repository=CoverageRecurrenceRepository(plane),
        result_repository=OntologyObservationResultRepository(plane),
        capability=_UnavailableObserver(),
        gap_validator=CoreCoverageGapValidator(plane),
    )

    result = runner.run(
        observation=observation, source_text="Alice mentors Bob."
    )

    assert result.observation.processing_state == DiscoveryProcessingState.UNAVAILABLE
    assert result.observation.semantic_outcome == CoverageSemanticOutcome.NOT_EVALUATED
    assert result.observation.downstream_failure_signature is not None
    assert result.recurrence_group is None

    reopened = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage_path))
    recovered = _runner(reopened, _gap_result()).recover_interrupted(
        source_loader=lambda _source_id: "Alice mentors Bob."
    )
    assert len(recovered) == 1
    assert recovered[0].observation.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert recovered[0].observation.semantic_outcome == CoverageSemanticOutcome.UNSUPPORTED_RELATION
    assert recovered[0].recurrence_group is not None


def test_restart_recovers_running_attempt_without_durable_result() -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = CoverageObservationRepository(plane)
    observation = _observation(
        1, lineage="a" * 64, session_id="session:one"
    )
    repository.create(observation)
    running = start_coverage_observation(observation)
    repository.replace(running, previous=observation)

    recovered = _runner(plane, _gap_result()).recover_interrupted(
        source_loader=lambda _source_id: "Alice mentors Bob."
    )

    assert len(recovered) == 1
    assert recovered[0].observation.processing_state == DiscoveryProcessingState.CLASSIFIED
    assert recovered[0].recurrence_group is not None
    assert recovered[0].recurrence_group.independent_lineage_count == 1


@pytest.mark.parametrize("failure_owner", ["gap", "group"])
def test_retry_rebuilds_incomplete_classified_projections(
    failure_owner: str,
) -> None:
    plane = MemoryPlaneService(record_store=InMemoryMemoryPlaneStore())
    repository = CoverageObservationRepository(plane)
    observation = _observation(
        1, lineage="a" * 64, session_id="session:one"
    )
    repository.create(observation)
    runner = _runner(plane, _gap_result())
    target = (
        VerifiedCoverageGapRepository
        if failure_owner == "gap"
        else CoverageRecurrenceRepository
    )
    method = "create" if failure_owner == "gap" else "write"
    with (
        patch.object(target, method, side_effect=OSError("injected crash")),
        pytest.raises(OSError, match="injected crash"),
    ):
        runner.run(
            observation=observation,
            source_text="Alice mentors Bob.",
        )

    classified = repository.load(observation.observation_id)
    assert classified is not None
    assert classified.processing_state == DiscoveryProcessingState.CLASSIFIED
    recovered = runner.run(
        observation=classified,
        source_text="Alice mentors Bob.",
    )
    assert recovered.recurrence_group is not None
    assert recovered.recurrence_group.independent_lineage_count == 1
