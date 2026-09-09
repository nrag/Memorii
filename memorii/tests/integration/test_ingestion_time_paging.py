"""Real registered cursor/retention behavior with a bounded fixture cohort."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from typing import TypeVar

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    SourceRetentionTimeAttestation,
    TransactionGroupCommitTimeAttestation,
)
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_paging import (
    AuthenticatedGraphObservationPagingRuntime,
    GraphObservationCohortInput,
    IngestionTimeObservationCohortInput,
    ObservationCohortUnavailableError,
    ObservationRetentionBudget,
    VerifiedGraphObservationAuthorization,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationPage,
    GraphObservationPagePolicySnapshot,
    GraphObservationRequest,
    IngestionTimeAttestationPage,
    IngestionTimeAttestationRequest,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import GraphObservationRecordKey
from memorii.core.memory_evolution.graph_observation_streams import EntityRevisionStreamRecord
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import (
    decode_registered_ingestion_time_attestation_cursor,
    decode_registered_observation_cursor,
    emit_registered_observation_artifact,
    issue_registered_ingestion_time_attestation_cursor,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import TrustedTypedValueArtifactVerificationKey
from memorii.core.memory_plane.service import MemoryPlaneService
from pydantic import BaseModel
from tests.fixtures.semantic_ingestion.observation_publication import observation_publication
from tests.unit.core.memory_evolution.test_graph_observation_public_contracts import _cohorts
from tests.unit.core.memory_evolution.test_graph_observation_streams import _entity_payload

_Model = TypeVar("_Model", bound=BaseModel)


@pytest.fixture
def paging(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "AuthenticatedGraphObservationContext", "GraphObservationAuthorizationDecision",
        "GraphObservationPagePolicySnapshot", "ResolvedGraphObservationCohort",
        "IngestionTimeObservationSnapshot", "IngestionTimeAttestationPage",
        "IngestionTimeAttestationCursorPayload", "GraphObservationCursorPayload",
        "GraphRecordObservationSnapshot", "GraphObservationPage",
    ))
    publication = history.publications[0]

    def emit(value: _Model) -> _Model:
        result = emit_registered_observation_artifact(
            value, schema_id=type(value).__name__, history=history,
            publication=publication, limits=limits,
        ).value
        assert isinstance(result, type(value))
        return result

    class Harness:
        context: AuthenticatedGraphObservationContext
        scope: MemoryScope
        expires_at: datetime
        runtime: AuthenticatedGraphObservationPagingRuntime
        request: IngestionTimeAttestationRequest
        graph_request: GraphObservationRequest
        attestations: tuple[SourceRetentionTimeAttestation, TransactionGroupCommitTimeAttestation]
        key: Ed25519PrivateKey
        codec: dict
        emit: Callable[[BaseModel], BaseModel]
        now_value = datetime(2026, 9, 8, tzinfo=UTC)
        denied = False
        outage = False
        cohort_failure = False
        expire_during_build = False
        empty = False
        entered: Event | None = None
        release: Event | None = None
        cohort_calls = 0
        policy_revision = "page-policy"
        scope_identity = "scope"

        def now(self):
            return self.now_value

        def resolve(self, **kwargs):
            if self.outage:
                raise OSError("identity provider unavailable")
            return self.context

        def authorize(self, *, purpose, **kwargs):
            assert purpose in {"ingestion_time_attestation", "graph_observation"}
            if self.denied:
                return None
            policy = emit(GraphObservationPagePolicySnapshot(
                policy_revision=self.policy_revision, minimum_total_page_size=1, maximum_total_page_size=10,
                cursor_schema_version=1, snapshot_maximum_age=timedelta(minutes=5), policy_digest="0" * 64,
            ))
            decision = emit(GraphObservationAuthorizationDecision(
                kind="authorized", authorized_scope_identity=self.scope_identity, policy_revision="policy",
                page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
                expires_at=self.expires_at, decision_digest="0" * 64,
            ))
            return VerifiedGraphObservationAuthorization(decision, policy, self.scope)

        def ingestion_time_input(self, *, snapshot, decision, authorized_scope, maximum_stream_records, maximum_snapshot_bytes, **kwargs):
            self.cohort_calls += 1
            assert authorized_scope == self.scope
            assert maximum_stream_records == self.runtime._retention_budget.maximum_stream_records
            assert maximum_snapshot_bytes == self.runtime._retention_budget.maximum_snapshot_bytes
            if self.entered is not None:
                self.entered.set()
                assert self.release is not None
                assert self.release.wait(10)
            if self.cohort_failure:
                raise ObservationCohortUnavailableError("not terminal")
            if self.expire_during_build:
                self.now_value = self.expires_at
            preimage = _cohorts()[0].model_copy(update={
                "memory_plane_write_revision": snapshot.memory_plane_write_revision,
                "authorization_decision_digest": decision.decision_digest,
                "authorized_scope_identity": decision.authorized_scope_identity,
                "changed_record_keys": (), "boundary_record_keys": (),
            })
            return IngestionTimeObservationCohortInput(preimage, () if self.empty else self.attestations)

        def graph_observation_input(self, **kwargs):
            ingested = self.ingestion_time_input(**kwargs)
            stream = () if self.empty else tuple(EntityRevisionStreamRecord(
                record_kind="entity_revision", primary_key=f"entity-{index}",
                record_digest=payload.record_digest, payload=payload,
            ) for index in (1, 2) for payload in (
                _entity_payload().model_copy(update={"entity_revision_id": f"entity-{index}"}),
            ))
            preimage = ingested.cohort_preimage.model_copy(update={"changed_record_keys": tuple(
                GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key)
                for item in stream
            )})
            return GraphObservationCohortInput(preimage, stream)

        def read_graph(self, request: GraphObservationRequest | None = None):
            return self.runtime.observe_graph(host_ingress="trusted", request=request or self.graph_request)

        def read(self, request: IngestionTimeAttestationRequest | None = None):
            return self.runtime.observe_ingestion_time_attestations(host_ingress="trusted", request=request or self.request)

    h = Harness()
    h.scope = MemoryScope(user_id="user")
    h.expires_at = h.now_value + timedelta(minutes=10)
    h.context = emit(AuthenticatedGraphObservationContext(
        principal_subject_id="principal", tenant_partition_id="tenant",
        authorized_scope_set_digest="a" * 64, authentication_session_id="session", context_digest="0" * 64,
    ))
    h.attestations = (
        emit(SourceRetentionTimeAttestation(
            kind="source_retention", attestation_id="source-time", source_id="source",
            operation_fence_id="fence", retained_at=h.now_value, graph_revision="graph",
            clock_identity="clock", source_record_digest="a" * 64, attestation_digest="0" * 64,
        )),
        emit(TransactionGroupCommitTimeAttestation(
            kind="transaction_group_commit", attestation_id="group-time", source_id="source",
            operation_fence_id="fence", transaction_group_id="group", operation_ids=("operation",),
            transaction_started_at=h.now_value, transaction_committed_at=h.now_value,
            graph_revision_before="before", graph_revision_after="graph", applied_graph_delta_digest="a" * 64,
            clock_identity="clock", committed_batch_digest="b" * 64, attestation_digest="0" * 64,
        )),
    )
    h.key = Ed25519PrivateKey.generate()
    h.codec = dict(history=history, publication=publication, limits=limits,
                   verification_key=TrustedTypedValueArtifactVerificationKey(h.key.public_key().public_bytes_raw()))
    h.runtime = AuthenticatedGraphObservationPagingRuntime(
        memory_plane=MemoryPlaneService(), context_resolver=h, authorizer=h, cohort_provider=h,
        protected_clock=h, registry_history=history, registry_publication=publication,
        cursor_signing_key=h.key, cursor_verification_key=h.codec["verification_key"], reader_limits=limits,
        correlation_token_factory=lambda: "correlation", retention_budget=ObservationRetentionBudget(
            maximum_stream_records=10, maximum_snapshot_bytes=100_000, maximum_retained_snapshots=1,
            maximum_retained_bytes=100_000, maximum_tenant_snapshots=1, maximum_tenant_bytes=100_000,
        ),
    )
    h.request = IngestionTimeAttestationRequest(
        scope_constraint=h.scope, cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("source",), seed_operation_ids=(), include_referenced_boundary_entities=True,
        ), expected_graph_revision="graph", expected_observation_revision="observation", total_page_size=1, cursor=None,
    )
    h.emit = emit
    h.graph_request = GraphObservationRequest(
        **h.request.model_dump(), view="current", valid_at=None, system_as_of=h.now_value,
    )
    return h


def test_registered_attestation_pages_verify_purpose_predecessor_and_current_authority(paging):
    h = paging
    first = h.read()
    assert isinstance(first, IngestionTimeAttestationPage) and first.next_cursor
    continuation = h.request.model_copy(update={"cursor": first.next_cursor})
    payload = decode_registered_ingestion_time_attestation_cursor(first.next_cursor, **h.codec)
    assert payload.request.model_dump() == h.request.model_dump(exclude={"cursor"})
    with pytest.raises(ValueError):
        decode_registered_observation_cursor(first.next_cursor, **h.codec)
    forged = issue_registered_ingestion_time_attestation_cursor(
        payload.model_copy(update={"preceding_attestation_id": "substituted"}), signing_key=h.key, **h.codec,
    )
    assert h.read(continuation.model_copy(update={"cursor": forged})).reason == "invalid_cursor"
    h.scope_identity = "different-authorized-scope"
    assert h.read(continuation).reason == "invalid_cursor"
    h.scope_identity = "scope"
    h.denied = True
    assert h.read(continuation.model_copy(update={"cursor": "not even encoded"})).reason == "revoked_access"
    h.denied = False
    second = h.read(continuation)
    assert isinstance(second, IngestionTimeAttestationPage) and second.next_cursor is None
    assert (*first.attestations, *second.attestations) == h.attestations
    assert h.cohort_calls == 1
    assert h.read(continuation).reason == "stale_cursor"
    assert isinstance(h.read(), IngestionTimeAttestationPage)


def test_capacity_reservations_survive_concurrent_build_and_release_on_failed_or_final_read(paging):
    h = paging
    h.cohort_failure = True
    assert h.read().reason == "denied"
    assert not h.runtime._reservations
    h.cohort_failure = False
    h.entered, h.release = Event(), Event()
    with ThreadPoolExecutor(max_workers=1) as executor:
        running = executor.submit(h.read)
        assert h.entered.wait(10)
        assert h.read().reason == "denied"
        h.release.set()
        first = running.result(timeout=20)
    assert isinstance(first, IngestionTimeAttestationPage)
    h.entered = None
    assert h.read().reason == "denied"
    final = h.read(h.request.model_copy(update={"cursor": first.next_cursor}))
    assert isinstance(final, IngestionTimeAttestationPage) and final.next_cursor is None
    h.empty = True
    empty = h.read()
    assert isinstance(empty, IngestionTimeAttestationPage) and not empty.attestations and empty.next_cursor is None
    h.empty = False
    h.expire_during_build = True
    assert h.read().reason == "denied"
    assert not h.runtime._reservations and not h.runtime._ingestion_snapshots


def test_authority_outage_is_non_disclosing_before_cohort_or_cursor_lookup(paging):
    h = paging
    h.outage = True
    assert h.read().reason == "denied"
    assert h.read(h.request.model_copy(update={"cursor": "bad"})).reason == "revoked_access"
    assert h.cohort_calls == 0


@pytest.mark.parametrize("limiting_field", [
    "maximum_retained_snapshots", "maximum_tenant_snapshots",
    "maximum_retained_bytes", "maximum_tenant_bytes",
])
def test_each_shared_capacity_dimension_limits_new_snapshot_without_evicting_live_token(paging, limiting_field):
    from dataclasses import replace

    h = paging
    limits = dict(maximum_retained_snapshots=10, maximum_tenant_snapshots=10,
                  maximum_retained_bytes=1_000_000, maximum_tenant_bytes=1_000_000)
    limits[limiting_field] = 1 if limiting_field.endswith("snapshots") else 100_000
    h.runtime._retention_budget = replace(h.runtime._retention_budget, **limits)
    first = h.read()
    assert isinstance(first, IngestionTimeAttestationPage) and first.next_cursor
    assert h.read().reason == "denied"
    final = h.read(h.request.model_copy(update={"cursor": first.next_cursor}))
    assert isinstance(final, IngestionTimeAttestationPage) and final.next_cursor is None
    assert isinstance(h.read(), IngestionTimeAttestationPage)


def test_unexpected_cohort_exception_releases_capacity_without_hiding_failure(paging, monkeypatch):
    h = paging
    original = h.ingestion_time_input

    def unavailable(**kwargs):
        raise RuntimeError("cohort construction failed")

    monkeypatch.setattr(h, "ingestion_time_input", unavailable)
    with pytest.raises(RuntimeError, match="cohort construction failed"):
        h.read()
    assert not h.runtime._reservations
    monkeypatch.setattr(h, "ingestion_time_input", original)
    assert isinstance(h.read(), IngestionTimeAttestationPage)


def test_snapshot_expiry_releases_quota_and_old_cursor_is_stale(paging):
    h = paging
    first = h.read()
    assert isinstance(first, IngestionTimeAttestationPage) and first.next_cursor
    h.now_value += timedelta(minutes=5)
    assert h.read(h.request.model_copy(update={"cursor": first.next_cursor})).reason == "stale_cursor"
    assert isinstance(h.read(), IngestionTimeAttestationPage)


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
@pytest.mark.parametrize("overflow", ["stream", "bytes"])
def test_snapshot_capacity_overflow_denies_and_releases_only_new_reservation(paging, endpoint, overflow):
    from dataclasses import replace

    h = paging
    read = h.read_graph if endpoint == "graph" else h.read
    request = h.graph_request if endpoint == "graph" else h.request
    first = read()
    assert first.next_cursor
    charge = next(iter(h.runtime._retained_bytes.values()))
    h.runtime._retention_budget = replace(h.runtime._retention_budget,
        maximum_retained_snapshots=3, maximum_tenant_snapshots=3,
        maximum_retained_bytes=1_000_000, maximum_tenant_bytes=1_000_000,
        **({"maximum_stream_records": 1} if overflow == "stream" else {"maximum_snapshot_bytes": charge - 1}),
    )
    assert read().reason == "denied"
    assert not h.runtime._reservations
    assert len(h.runtime._retained_bytes) == 1
    final = read(request.model_copy(update={"cursor": first.next_cursor}))
    assert final.kind == "page" and final.next_cursor is None
    assert not h.runtime._retained_bytes


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
def test_snapshot_policy_age_expires_during_construction(paging, monkeypatch, endpoint):
    h = paging
    original = h.ingestion_time_input

    def slow(**kwargs):
        result = original(**kwargs)
        h.now_value += timedelta(minutes=5)
        return result

    monkeypatch.setattr(h, "ingestion_time_input", slow)
    assert (h.read_graph() if endpoint == "graph" else h.read()).reason == "denied"
    assert not h.runtime._retained_bytes and not h.runtime._reservations


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
def test_snapshot_creation_time_is_distinct_from_authorization_time_and_sets_retention_deadline(
    paging, monkeypatch, endpoint,
):
    h = paging
    authorization_time = h.now_value
    original_authorize = h.authorize

    def advance_after_authorization(**kwargs):
        result = original_authorize(**kwargs)
        h.now_value += timedelta(minutes=1)
        return result

    monkeypatch.setattr(h, "authorize", advance_after_authorization)
    page = h.read_graph() if endpoint == "graph" else h.read()
    assert page.kind == "page" and page.next_cursor
    retained = next(iter(
        h.runtime._graph_snapshots.values() if endpoint == "graph" else h.runtime._ingestion_snapshots.values()
    ))
    locked_time = authorization_time + timedelta(minutes=1)
    assert retained.snapshot.created_at == locked_time
    assert retained.expires_at == locked_time + timedelta(minutes=5)


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
@pytest.mark.parametrize("mutation", ["control", "empty_batch"])
def test_continuation_fences_writes_that_do_not_advance_data_revision(paging, endpoint, mutation):
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility

    h = paging
    read = h.read_graph if endpoint == "graph" else h.read
    request = h.graph_request if endpoint == "graph" else h.request
    first = read()
    assert first.kind == "page" and first.next_cursor
    plane = h.runtime._memory_plane
    data_revision, _ = plane.read_snapshot()
    write_revision, _ = plane.read_write_snapshot()
    records = () if mutation == "empty_batch" else (CanonicalMemoryRecord(
        memory_id="observation-control", domain=MemoryDomain.SEMANTIC,
        text="internal control", content={}, status=CommitStatus.COMMITTED,
        source_kind="observation_control_test", timestamp=h.now_value,
        visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    ),)
    plane.conditionally_write_records(records, preconditions=())
    assert plane.read_snapshot()[0] == data_revision
    assert plane.read_write_snapshot()[0] == write_revision + 1
    response = read(request.model_copy(update={"cursor": first.next_cursor}))
    assert response.kind == "failure" and response.reason == "stale_cursor"
    assert not h.runtime._graph_snapshots and not h.runtime._ingestion_snapshots
    assert not h.runtime._reservations and not h.runtime._retained_bytes


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
def test_first_page_revision_race_denies_without_retaining_snapshot(paging, monkeypatch, endpoint):
    from memorii.core.memory_plane.models import CanonicalMemoryRecord
    from memorii.domain.enums import CommitStatus, MemoryDomain

    h = paging
    original = h.runtime._emit

    def intervening_write(value, schema_id):
        result = original(value, schema_id)
        if isinstance(value, (GraphObservationPage, IngestionTimeAttestationPage)):
            h.runtime._memory_plane.write_records((CanonicalMemoryRecord(
                memory_id="concurrent", domain=MemoryDomain.EXECUTION, text="write", content={},
                status=CommitStatus.COMMITTED, source_kind="test", timestamp=h.now_value,
            ),))
        return result

    monkeypatch.setattr(h.runtime, "_emit", intervening_write)
    assert (h.read_graph() if endpoint == "graph" else h.read()).reason == "denied"
    assert not h.runtime._retained_bytes and not h.runtime._reservations


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
def test_decode_time_expiry_precedes_policy_change(paging, monkeypatch, endpoint):
    h = paging
    read = h.read_graph if endpoint == "graph" else h.read
    request = h.graph_request if endpoint == "graph" else h.request
    decoder_name = "_decode_cursor" if endpoint == "graph" else "_decode_ingestion_cursor"
    first = read()
    original = getattr(h.runtime, decoder_name)

    def expire(cursor):
        result = original(cursor)
        h.now_value = h.expires_at
        return result

    monkeypatch.setattr(h.runtime, decoder_name, expire)
    h.policy_revision = "new-policy"
    assert read(request.model_copy(update={"cursor": first.next_cursor})).reason == "revoked_access"
    assert not h.runtime._retained_bytes


@pytest.mark.parametrize("first_endpoint", ["graph", "ingestion"])
def test_graph_and_ingestion_share_capacity_and_final_release(paging, first_endpoint):
    h = paging
    first_read, second_read = (h.read_graph, h.read) if first_endpoint == "graph" else (h.read, h.read_graph)
    request = h.graph_request if first_endpoint == "graph" else h.request
    first = first_read()
    assert second_read().reason == "denied"
    assert first_read(request.model_copy(update={"cursor": first.next_cursor})).next_cursor is None
    assert second_read().kind == "page"


def test_tenant_and_global_capacity_are_distinct_and_do_not_evict(paging):
    from dataclasses import replace

    h = paging
    h.runtime._retention_budget = replace(h.runtime._retention_budget,
        maximum_retained_snapshots=2, maximum_retained_bytes=1_000_000,
        maximum_tenant_snapshots=1, maximum_tenant_bytes=1_000_000,
    )
    context_a = h.context
    page_a = h.read()
    assert h.read().reason == "denied"
    h.context = h.emit(context_a.model_copy(update={"tenant_partition_id": "other-tenant", "context_digest": "0" * 64}))
    page_b = h.read()
    assert page_b.kind == "page"
    assert h.read().reason == "denied"
    h.context = h.emit(context_a.model_copy(update={"tenant_partition_id": "third-tenant", "context_digest": "0" * 64}))
    assert h.read().reason == "denied"
    h.context = context_a
    assert h.read(h.request.model_copy(update={"cursor": page_a.next_cursor})).kind == "page"
    h.context = h.emit(context_a.model_copy(update={"tenant_partition_id": "other-tenant", "context_digest": "0" * 64}))
    assert h.read(h.request.model_copy(update={"cursor": page_b.next_cursor})).kind == "page"


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
def test_policy_change_releases_own_stale_cursor_charge(paging, endpoint):
    h = paging
    read = h.read_graph if endpoint == "graph" else h.read
    request = h.graph_request if endpoint == "graph" else h.request
    first = read()
    h.policy_revision = "new-policy"
    assert read(request.model_copy(update={"cursor": first.next_cursor})).reason == "stale_cursor"
    assert not h.runtime._retained_bytes
    assert read().kind == "page"


@pytest.mark.parametrize("endpoint", ["graph", "ingestion"])
def test_policy_mismatch_cannot_evict_another_authenticated_callers_cursor(paging, endpoint):
    h = paging
    read = h.read_graph if endpoint == "graph" else h.read
    request = h.graph_request if endpoint == "graph" else h.request
    original_context = h.context
    first = read()
    h.context = h.emit(original_context.model_copy(update={"authentication_session_id": "other-session", "context_digest": "0" * 64}))
    h.policy_revision = "new-policy"
    assert read(request.model_copy(update={"cursor": first.next_cursor})).reason == "stale_cursor"
    assert len(h.runtime._retained_bytes) == 1
    h.context = original_context
    h.policy_revision = "page-policy"
    assert read(request.model_copy(update={"cursor": first.next_cursor})).kind == "page"
