"""Focused proof for the detached cohort materialization provider.

The provider is exercised directly against the real activated atomic-store
backend reused from the detached-cohort integration harness: one committed
fact source, one detached observation authority, and one merged observation
stream containing both ingestion records and native projection records with
real registered digests.  No fixture cohort stands in for the backend.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.graph_effect_contracts import (
    IngestionObservationDelta,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCohortSelector,
)
from memorii.core.memory_evolution.graph_observation_materialization import (
    AtomicStoreGraphObservationCohortProvider,
    _merge_observation_streams,
)
from memorii.core.memory_evolution.graph_observation_paging import (
    DetachedGraphObservationRecords,
    ObservationCohortUnavailableError,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationRequest,
    GraphObservationRequestCoordinates,
    IngestionTimeAttestationRequest,
    IngestionTimeAttestationRequestCoordinates,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationRecordKey,
)
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from tests.integration.test_observation_ledger_activation import (
    _provider_factory,
    _seed_provider,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    _host_ingress,
)

_SNAPSHOT_TIME = datetime(2026, 9, 9, tzinfo=UTC)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_INGESTION_KINDS = frozenset({
    "source_introduction", "operation_introduction",
    "operation_terminal_outcome", "source_terminal_outcome",
})
_NATIVE_KINDS = frozenset({
    "entity_revision", "claim_assertion", "relation", "citation", "provenance",
})
_MAXIMUM_STREAM_RECORDS = 1000
_MAXIMUM_SNAPSHOT_BYTES = 10_000_000


@pytest.fixture(scope="module")
def backend(tmp_path_factory, request):
    """One real activated provider with a committed fact, read back detached."""
    patch = pytest.MonkeyPatch()
    # The store re-verifies its installed activation target on every detached
    # read, so the isolated package metadata must stay patched until the last
    # test of this module finished; only then is it restored.
    request.addfinalizer(patch.undo)
    tmp_path = tmp_path_factory.mktemp("materialization")
    build, _, _ = _provider_factory(
        tmp_path, patch, normalization=True, complete_registry=True,
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "ledger-store"))
    provider = build(plane)
    _seed_provider(provider)
    provider.activate_observation_ledger()
    result = provider.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="materialization-source", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result is not None
    runtime = provider._composed_semantic_runtime
    assert (
        runtime is not None
        and runtime.atomic_store is not None
        and runtime.typed_value_registry_history is not None
        and runtime.observation_activation_target is not None
    )
    revision, records = plane.read_write_snapshot()
    authority = runtime.atomic_store.read_detached_observation_authority(
        write_revision=revision, records=records,
        snapshot_created_at=_SNAPSHOT_TIME,
    )
    group_entry = next(
        entry for entry in authority.observation.entries
        if isinstance(entry.delta, IngestionObservationDelta)
    )
    finalization = next(
        entry for entry in authority.observation.entries
        if isinstance(entry.delta, SourceFinalizationObservationDelta)
    )
    cohort_provider = AtomicStoreGraphObservationCohortProvider(
        atomic_store=runtime.atomic_store,
        registry_history=runtime.typed_value_registry_history,
        registry_publication=runtime.observation_activation_target.publication,
        limits=runtime.atomic_store._observation_artifact_limits,
    )
    grant = MemoryScope(user_id="user:alice", task_id="task:one")
    context = AuthenticatedGraphObservationContext(
        principal_subject_id="user:alice",
        tenant_partition_id=finalization.delta.required_outcome_scopes.tenant_partition_id,
        authorized_scope_set_digest="a" * 64,
        authentication_session_id="test-session",
        context_digest="b" * 64,
    )
    decision = GraphObservationAuthorizationDecision(
        kind="authorized", authorized_scope_identity="scope", policy_revision="policy",
        page_policy_revision="page-policy", page_policy_digest="0" * 64,
        expires_at=_SNAPSHOT_TIME + timedelta(hours=1), decision_digest="c" * 64,
    )
    selector = GraphObservationCohortSelector(
        seed_source_ids=(group_entry.delta.source_id,),
        seed_operation_ids=(),
        include_referenced_boundary_entities=True,
    )
    coordinates = GraphObservationRequestCoordinates(
        scope_constraint=grant, cohort_selector=selector, view="current",
        expected_graph_revision=authority.graph.graph_revision,
        expected_observation_revision=authority.observation.head.observation_revision,
        valid_at=None, system_as_of=_SNAPSHOT_TIME, total_page_size=100,
    )
    time_coordinates = IngestionTimeAttestationRequestCoordinates(
        scope_constraint=grant, cohort_selector=selector,
        expected_graph_revision=authority.graph.graph_revision,
        expected_observation_revision=authority.observation.head.observation_revision,
        total_page_size=100,
    )
    return SimpleNamespace(
        provider=cohort_provider,
        snapshot=DetachedGraphObservationRecords(
            memory_plane_write_revision=revision, records=records,
            created_at=_SNAPSHOT_TIME,
        ),
        authority=authority, context=context, decision=decision, grant=grant,
        coordinates=coordinates, time_coordinates=time_coordinates,
    )


def _cohort_input(backend, **overrides):
    values = dict(
        snapshot=backend.snapshot,
        context=backend.context,
        decision=backend.decision,
        authorized_scope=backend.grant,
        request=backend.coordinates,
        maximum_stream_records=_MAXIMUM_STREAM_RECORDS,
        maximum_snapshot_bytes=_MAXIMUM_SNAPSHOT_BYTES,
    )
    values.update(overrides)
    return backend.provider.graph_observation_input(**values)


def test_merged_stream_contains_ingestion_and_native_records(backend):
    cohort = _cohort_input(backend)
    kinds = [item.record_kind for item in cohort.stream]
    identities = [(item.record_kind, item.primary_key) for item in cohort.stream]
    assert kinds == sorted(kinds)
    assert len(identities) == len(set(identities))
    assert set(kinds) >= _INGESTION_KINDS
    assert set(kinds) >= _NATIVE_KINDS
    for record in cohort.stream:
        assert _HEX64.fullmatch(record.record_digest)
        assert record.record_digest != "0" * 64
        assert record.record_digest == record.payload.record_digest
        if "system_interval" in type(record.payload).model_fields:
            assert record.payload.system_interval == TimeInterval(start=_SNAPSHOT_TIME)
        if "boundary" in type(record.payload).model_fields:
            assert record.payload.boundary is False
    claim = next(item for item in cohort.stream if item.record_kind == "claim_assertion")
    assert claim.payload.polarity == "positive"
    assert claim.payload.policy_fingerprints == tuple(sorted(set(claim.payload.policy_fingerprints)))
    preimage = cohort.cohort_preimage
    assert preimage.changed_record_keys == tuple(
        GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key)
        for item in cohort.stream
    )
    assert preimage.boundary_record_keys == ()
    assert len(preimage.graph_revision_delta_ids) == 1
    assert preimage.graph_revision_delta_digests == tuple(
        delta.delta_digest for delta in backend.authority.graph_deltas
    )
    assert preimage.graph_revision == backend.authority.graph.graph_revision
    assert preimage.observation_revision == backend.authority.observation.head.observation_revision
    assert preimage.memory_plane_write_revision == backend.snapshot.memory_plane_write_revision
    assert preimage.authorization_decision_digest == backend.decision.decision_digest
    assert preimage.authorized_scope_identity == backend.decision.authorized_scope_identity


def test_duplicate_merged_identity_denies(backend):
    cohort = _cohort_input(backend)
    ingestion = tuple(
        item for item in cohort.stream if item.record_kind in _INGESTION_KINDS
    )
    native = tuple(
        item for item in cohort.stream if item.record_kind in _NATIVE_KINDS
    )
    assert ingestion and native
    assert _merge_observation_streams(ingestion, native) == cohort.stream
    with pytest.raises(
        ObservationCohortUnavailableError, match="duplicate record identity",
    ):
        _merge_observation_streams(ingestion, (*native, native[0]))
    cross = tuple(item for item in native if item.record_kind != native[0].record_kind)
    with pytest.raises(
        ObservationCohortUnavailableError, match="duplicate record identity",
    ):
        _merge_observation_streams(ingestion, (*cross, native[0], native[0]))


def test_revision_mismatch_denies(backend):
    with pytest.raises(
        ObservationCohortUnavailableError, match="graph revision differs from request",
    ):
        _cohort_input(
            backend,
            request=backend.coordinates.model_copy(
                update={"expected_graph_revision": "graph:other"},
            ),
        )
    with pytest.raises(
        ObservationCohortUnavailableError, match="observation revision differs from request",
    ):
        _cohort_input(
            backend,
            request=backend.coordinates.model_copy(
                update={"expected_observation_revision": "observation:other"},
            ),
        )


def test_ingestion_time_input_remains_fail_closed(backend):
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="persisted ingestion-time attestations are unavailable",
    ):
        backend.provider.ingestion_time_input(
            snapshot=backend.snapshot,
            context=backend.context,
            decision=backend.decision,
            authorized_scope=backend.grant,
            request=backend.time_coordinates,
            maximum_stream_records=_MAXIMUM_STREAM_RECORDS,
            maximum_snapshot_bytes=_MAXIMUM_SNAPSHOT_BYTES,
        )


@pytest.mark.parametrize("cursor", (None, "untrusted-token"))
def test_unconfigured_public_observation_never_reads_seeds(monkeypatch, cursor):
    service = build_provider_memory_service_from_env()

    def unexpected_read(*args, **kwargs):
        raise AssertionError("unconfigured observation read the memory plane")

    monkeypatch.setattr(service._memory_plane, "read_write_snapshot", unexpected_read)
    monkeypatch.setattr(service._memory_plane, "read_timed_write_snapshot", unexpected_read)
    ingress = AuthenticatedHostIngress(
        provider_identity="host", principal_handle=object(), session_handle=object(),
        received_at=_SNAPSHOT_TIME,
    )
    selector = GraphObservationCohortSelector(
        seed_source_ids=("unknown",), seed_operation_ids=(),
        include_referenced_boundary_entities=True,
    )
    graph_request = GraphObservationRequest(
        scope_constraint=MemoryScope(user_id="alice"), cohort_selector=selector,
        expected_graph_revision="graph", expected_observation_revision="observation",
        total_page_size=1, cursor=cursor, view="current", valid_at=None,
        system_as_of=_SNAPSHOT_TIME,
    )
    time_request = IngestionTimeAttestationRequest(
        scope_constraint=graph_request.scope_constraint, cohort_selector=selector,
        expected_graph_revision="graph", expected_observation_revision="observation",
        total_page_size=1, cursor=cursor,
    )
    graph_response = service.observe_graph(host_ingress=ingress, request=graph_request)
    time_response = service.observe_ingestion_time_attestations(
        host_ingress=ingress, request=time_request,
    )
    for response in (graph_response, time_response):
        assert response.kind == "failure"
        assert response.reason == ("denied" if cursor is None else "revoked_access")
        assert set(response.model_dump()) == {"kind", "reason", "request_correlation_token"}
    assert graph_response.request_correlation_token != time_response.request_correlation_token
