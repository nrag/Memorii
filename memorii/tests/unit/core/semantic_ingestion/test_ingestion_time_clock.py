"""Protected ingestion clock tests (M0: ingestion-time persistence).

The protected clock is the single retention-time authority: raw-source
construction samples it once per admission, the caller-owned event timestamp
stays delivery identity, and an exact redelivery reuses the winner's retained
record and governance material verbatim (recovery-before-derivation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
)
from memorii.core.memory_evolution.atomic_store import (
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.delivery_coordinate_migration import (
    DeliveryCoordinateMigrationCheckpoint,
    activate_migration,
    build_migration_plan,
    certify_migration,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    DeliveryIdentity,
    encode_typed_value,
)
from memorii.core.memory_evolution.ingestion_time_clock import IngestionTimeClock
from memorii.core.memory_evolution.record_projection import (
    source_observation_from_record,
)
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.ingestion import ProviderIngestionCoordinator
from memorii.core.provider.models import ProviderOperation
from tests.unit.core.semantic_ingestion.test_bootstrap_source_admission import (
    _binding,
    _service_with_capability,
    _TestHostBootstrapCapability,
)

CLOCK_NOW = datetime(2026, 5, 5, 12, 0, tzinfo=UTC)
CALLER_EVENT_TIME = datetime(2020, 1, 1, 9, 30, tzinfo=UTC)
LATER_CALLER_EVENT_TIME = datetime(2021, 7, 7, 8, 0, tzinfo=UTC)
ZERO_OFFSET_TZ = timezone(timedelta(0))
NON_UTC_TZ = timezone(timedelta(hours=2))


def _host_ingress() -> AuthenticatedHostIngress:
    return AuthenticatedHostIngress(
        provider_identity="provider:test",
        principal_handle=object(),
        session_handle=object(),
        received_at=datetime.now(UTC),
    )


def _source_id(delivery_id: str) -> str:
    identity = DeliveryIdentity.create(_binding(), delivery_id)
    return f"semantic_ingestion:source:{identity.delivery_key_digest}"


def _bind_admission_clock(service, samples: list[datetime]) -> None:
    """Bind a dedicated advancing sampler to the coordinator's clock owner.

    The service-level clock also serves ingress resolution and generic
    provider records, so the admission sample count is observed on the
    coordinator's protected clock itself.  The list grows by one on every
    admission sample: ``samples[0]`` is the seed, each following entry one
    protected sample.
    """

    def sample() -> datetime:
        value = samples[-1] + timedelta(minutes=len(samples))
        samples.append(value)
        return value

    service._provider_ingestion._clock = IngestionTimeClock(
        identity="test-admission-clock", now_provider=sample
    )


def _cutover_race(monkeypatch: pytest.MonkeyPatch, service) -> list[bool]:
    """Force exactly one writer-cutover retry inside one admission attempt."""
    original_admit = service._semantic_atomic_store.admit_source
    raced = [False]

    def cutover_then_admit(*, prepared, writer_binding):
        if not raced[0]:
            raced[0] = True
            plan = build_migration_plan(
                migration_plan_id="clock-race", source_writer_epoch=1,
                legacy_snapshot_token=sha256(encode_typed_value(())).hexdigest(), entries=(),
            )
            values = {
                "migration_plan_id": plan.migration_plan_id, "plan_digest": plan.plan_digest,
                "completed_entry_digests": (), "target_generation": 1,
            }
            checkpoint = DeliveryCoordinateMigrationCheckpoint(
                **values, checkpoint_digest=sha256(encode_typed_value(values)).hexdigest()
            )
            certificate = certify_migration(
                plan, checkpoint, independent_verifier_fingerprint="verifier"
            )
            service._semantic_writer_admission.transition(
                expected=writer_binding, admission_id="provider:2", runtime_mode="evidence_only",
                writer_implementation_fingerprint="provider:2", graph_schema_fingerprint="schema:2",
                migration_activation=activate_migration(plan, certificate), migration_plan=plan,
                migration_checkpoint=checkpoint, migration_certificate=certificate, target_records=(),
            )
        return original_admit(
            prepared=prepared,
            writer_binding=service._provider_ingestion._writer_admission.commit_binding(
                service._provider_ingestion._writer_admission.current()
            ),
        )

    monkeypatch.setattr(
        service._semantic_atomic_store, "publish_admitted_source", cutover_then_admit
    )
    return raced


def test_ingestion_time_clock_construction_requires_both_members() -> None:
    def fixed() -> datetime:
        return CLOCK_NOW

    with pytest.raises(TypeError):
        IngestionTimeClock(now_provider=fixed)
    with pytest.raises(TypeError):
        IngestionTimeClock(identity="test-clock")
    with pytest.raises(ValueError, match="identity is required"):
        IngestionTimeClock(identity="", now_provider=fixed)
    with pytest.raises(TypeError, match="callable now provider"):
        IngestionTimeClock(identity="test-clock", now_provider=CLOCK_NOW)
    clock = IngestionTimeClock(identity="test-clock", now_provider=fixed)
    assert clock.identity == "test-clock"
    assert clock.now_utc() == CLOCK_NOW


def test_ingestion_time_clock_rejects_naive_and_non_utc_samples() -> None:
    naive = IngestionTimeClock(
        identity="test-clock", now_provider=lambda: CLOCK_NOW.replace(tzinfo=None)
    )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        naive.now_utc()
    non_utc = IngestionTimeClock(
        identity="test-clock", now_provider=lambda: CLOCK_NOW.astimezone(NON_UTC_TZ)
    )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        non_utc.now_utc()
    zero_offset = IngestionTimeClock(
        # A zero-offset tzinfo that is not timezone.utc still normalizes to UTC.
        identity="test-clock",
        now_provider=lambda: CLOCK_NOW.replace(tzinfo=ZERO_OFFSET_TZ),
    )
    assert zero_offset.now_utc() == CLOCK_NOW


def test_provider_ingestion_coordinator_fails_closed_without_clock() -> None:
    plane = MemoryPlaneService()
    writers = SemanticWriterAdmissionStore(
        plane, bounded_preplanning_ownership_manifest()
    )
    store = SemanticIngestionAtomicStore(plane, writers)
    dependencies = {
        "memory_plane": plane,
        "admission_service": GovernedSourceAdmissionService(plane),
        "bootstrap_profile": None,
        "bootstrap_unavailable_reason": "invalid_config",
        "atomic_store": store,
        "writer_admission": writers,
    }
    with pytest.raises(TypeError, match="clock"):
        ProviderIngestionCoordinator(**dependencies)
    coordinator = ProviderIngestionCoordinator(
        **dependencies,
        clock=IngestionTimeClock(identity="test-clock", now_provider=lambda: CLOCK_NOW),
    )
    assert coordinator is not None


def test_retained_source_time_is_the_protected_sample_not_caller_event_time() -> None:
    plane = MemoryPlaneService()
    clock = IngestionTimeClock(identity="test-clock", now_provider=lambda: CLOCK_NOW)
    service = _service_with_capability(
        _TestHostBootstrapCapability(), memory_plane=plane, clock=clock
    )
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="clock-delivery",
        task_id="task:one",
        timestamp=CALLER_EVENT_TIME,
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    source = plane.get_record(_source_id("clock-delivery"))
    assert source is not None
    assert source.timestamp == CLOCK_NOW
    assert source.timestamp != CALLER_EVENT_TIME
    # The one sample also supplies both governance times: the sealed Step-1
    # observation reloads the retained record, never the caller event time.
    observation = source_observation_from_record(source)
    assert observation.timestamp == CLOCK_NOW


def test_metadata_poor_snapshot_time_is_the_protected_sample() -> None:
    plane = MemoryPlaneService()
    clock = IngestionTimeClock(identity="test-clock", now_provider=lambda: CLOCK_NOW)
    service = _service_with_capability(
        _TestHostBootstrapCapability(), memory_plane=plane, clock=clock
    )
    result = service.sync_event(
        operation=ProviderOperation.SESSION_END,
        content="user: Atlas owner is Bob.",
        operation_id="clock-session-end",
        task_id="task:one",
        timestamp=CALLER_EVENT_TIME,
        authenticated_host_ingress=_host_ingress(),
    )
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    snapshot = plane.get_record(_source_id("clock-session-end"))
    assert snapshot is not None
    assert snapshot.source_kind == "semantic_ingestion_metadata_poor_snapshot"
    assert snapshot.timestamp == CLOCK_NOW
    assert snapshot.timestamp != CALLER_EVENT_TIME


def test_exact_redelivery_reuses_winner_retained_material() -> None:
    plane = MemoryPlaneService()
    samples = [datetime(2026, 5, 5, tzinfo=UTC)]
    clock = IngestionTimeClock(identity="test-clock", now_provider=lambda: samples[-1])
    service = _service_with_capability(
        _TestHostBootstrapCapability(), memory_plane=plane, clock=clock
    )
    ingress = _host_ingress()
    first = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="clock-redelivery",
        task_id="task:one",
        timestamp=CALLER_EVENT_TIME,
        authenticated_host_ingress=ingress,
    )
    assert first.blocked_reasons["semantic_ingestion"] == "source_only"
    winner = plane.get_record(_source_id("clock-redelivery"))
    assert winner is not None
    first_retention = winner.timestamp
    records_after_first = plane.list_records()

    # The protected clock advances and the caller presents a different event
    # timestamp: neither may relabel the winner or re-derive its material.
    samples.append(first_retention + timedelta(days=30))

    second = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="clock-redelivery",
        task_id="task:one",
        timestamp=LATER_CALLER_EVENT_TIME,
        authenticated_host_ingress=ingress,
    )
    assert second.blocked_reasons["semantic_ingestion"] == "source_only"
    assert second.transcript_ids == first.transcript_ids
    retained = plane.get_record(_source_id("clock-redelivery"))
    assert retained == winner
    assert retained.timestamp == first_retention
    # No re-derived admission evidence appeared: the winner's byte set is the
    # complete record set for both deliveries.
    assert plane.list_records() == records_after_first


def test_metadata_poor_redelivery_reuses_winner_snapshot() -> None:
    plane = MemoryPlaneService()
    samples = [datetime(2026, 6, 1, tzinfo=UTC)]
    clock = IngestionTimeClock(identity="test-clock", now_provider=lambda: samples[-1])
    service = _service_with_capability(
        _TestHostBootstrapCapability(), memory_plane=plane, clock=clock
    )
    ingress = _host_ingress()
    first = service.sync_event(
        operation=ProviderOperation.SESSION_END,
        content="user: Atlas owner is Bob.",
        operation_id="clock-session-redelivery",
        task_id="task:one",
        timestamp=CALLER_EVENT_TIME,
        authenticated_host_ingress=ingress,
    )
    assert first.blocked_reasons["semantic_ingestion"] == "source_only"
    winner = plane.get_record(_source_id("clock-session-redelivery"))
    assert winner is not None
    first_retention = winner.timestamp
    records_after_first = plane.list_records()

    samples.append(first_retention + timedelta(days=30))

    second = service.sync_event(
        operation=ProviderOperation.SESSION_END,
        content="user: Atlas owner is Bob.",
        operation_id="clock-session-redelivery",
        task_id="task:one",
        timestamp=LATER_CALLER_EVENT_TIME,
        authenticated_host_ingress=ingress,
    )
    assert second.blocked_reasons["semantic_ingestion"] == "source_only"
    retained = plane.get_record(_source_id("clock-session-redelivery"))
    assert retained == winner
    assert retained.timestamp == first_retention
    assert plane.list_records() == records_after_first


def test_one_admission_sample_no_resampling_across_writer_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane = MemoryPlaneService()
    service = _service_with_capability(_TestHostBootstrapCapability(), memory_plane=plane)
    samples = [datetime(2026, 5, 5, tzinfo=UTC)]
    _bind_admission_clock(service, samples=samples)
    raced = _cutover_race(monkeypatch, service)
    result = service.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN,
        content="Atlas owner is Bob.",
        operation_id="clock-writer-retry",
        task_id="task:one",
        timestamp=CALLER_EVENT_TIME,
        authenticated_host_ingress=_host_ingress(),
    )
    assert raced[0]
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    # The writer-cutover race re-prepared the admission exactly once, yet the
    # protected clock was sampled exactly once: no resampling across retries
    # within one attempt.
    assert len(samples) == 2  # seed + exactly one admission sample
    source = plane.get_record(_source_id("clock-writer-retry"))
    assert source is not None
    assert source.timestamp == samples[1]


def test_metadata_poor_retry_never_resamples_the_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plane = MemoryPlaneService()
    service = _service_with_capability(_TestHostBootstrapCapability(), memory_plane=plane)
    samples = [datetime(2026, 6, 1, tzinfo=UTC)]
    _bind_admission_clock(service, samples=samples)
    raced = _cutover_race(monkeypatch, service)
    result = service.sync_event(
        operation=ProviderOperation.SESSION_END,
        content="user: Atlas owner is Bob.",
        operation_id="clock-session-writer-retry",
        task_id="task:one",
        timestamp=CALLER_EVENT_TIME,
        authenticated_host_ingress=_host_ingress(),
    )
    assert raced[0]
    assert result.blocked_reasons["semantic_ingestion"] == "source_only"
    assert len(samples) == 2  # seed + exactly one admission sample
    snapshot = plane.get_record(_source_id("clock-session-writer-retry"))
    assert snapshot is not None
    assert snapshot.timestamp == samples[1]
