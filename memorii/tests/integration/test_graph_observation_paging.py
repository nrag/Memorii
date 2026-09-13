"""Registered paging mechanics; the cohort collaborator is intentionally a fixture."""

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_paging import (
    AuthenticatedGraphObservationPagingRuntime,
    GraphObservationCohortInput,
    GraphObservationPagingError,
    ObservationRetentionBudget,
    VerifiedGraphObservationAuthorization,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationPage,
    GraphObservationPagePolicySnapshot,
    GraphObservationRequest,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import GraphObservationRecordKey
from memorii.core.memory_evolution.graph_observation_streams import EntityRevisionStreamRecord
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import emit_registered_observation_artifact
from memorii.core.memory_evolution.typed_value_artifact_integrity import TrustedTypedValueArtifactVerificationKey
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.domain.enums import CommitStatus, MemoryDomain
from tests.fixtures.semantic_ingestion.observation_publication import observation_publication
from tests.unit.core.memory_evolution.test_graph_observation_public_contracts import _cohorts
from tests.unit.core.memory_evolution.test_graph_observation_streams import _entity_payload


def test_registered_pages_reauthorize_and_fence_request_and_full_write_revision(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "AuthenticatedGraphObservationContext", "GraphObservationAuthorizationDecision",
        "GraphObservationPagePolicySnapshot", "GraphObservationCohortPreimage",
        "ResolvedGraphObservationCohort", "GraphRecordObservationSnapshot",
        "GraphObservationPage", "GraphObservationCursorPayload",
    ))

    def emit(value):
        return emit_registered_observation_artifact(
            value, schema_id=type(value).__name__, history=history,
            publication=history.publications[0], limits=limits,
        ).value

    now = datetime(2026, 9, 8, tzinfo=UTC)
    context = emit(AuthenticatedGraphObservationContext(
        principal_subject_id="principal", tenant_partition_id="tenant",
        authorized_scope_set_digest="a" * 64, authentication_session_id="session",
        context_digest="0" * 64,
    ))
    policy = emit(GraphObservationPagePolicySnapshot(
        policy_revision="page-policy", minimum_total_page_size=1, maximum_total_page_size=10,
        cursor_schema_version=1, snapshot_maximum_age=timedelta(minutes=5), policy_digest="0" * 64,
    ))
    decision = emit(GraphObservationAuthorizationDecision(
        kind="authorized", authorized_scope_identity="scope", policy_revision="policy",
        page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
        expires_at=now + timedelta(minutes=10), decision_digest="0" * 64,
    ))
    calls = []
    denied = False
    wrong_revision = False

    class Authority:
        def now(self):
            return now

        def resolve(self, **kwargs):
            calls.append("context")
            return context

        def authorize(self, **kwargs):
            calls.append("authorize")
            return None if denied else VerifiedGraphObservationAuthorization(
                decision=decision, page_policy=policy, authorized_scope=MemoryScope(user_id="user"),
            )

        def graph_observation_input(self, *, snapshot, **kwargs):
            calls.append("cohort")
            stream = tuple(EntityRevisionStreamRecord(
                record_kind="entity_revision", primary_key=f"entity-{index}",
                record_digest=payload.record_digest, payload=payload,
            ) for index in (1, 2) for payload in (
                _entity_payload().model_copy(update={"entity_revision_id": f"entity-{index}"}),
            ))
            preimage = _cohorts()[0].model_copy(update={
                "memory_plane_write_revision": snapshot.memory_plane_write_revision + int(wrong_revision),
                "authorization_decision_digest": decision.decision_digest,
                "changed_record_keys": tuple(GraphObservationRecordKey(
                    record_kind=item.record_kind, primary_key=item.primary_key,
                ) for item in stream),
            })
            return GraphObservationCohortInput(preimage, stream)

    plane = MemoryPlaneService()
    authority = Authority()
    key = Ed25519PrivateKey.generate()
    runtime = AuthenticatedGraphObservationPagingRuntime(
        memory_plane=plane, context_resolver=authority,
        authorizer=authority, cohort_provider=authority, protected_clock=authority,
        registry_history=history, registry_publication=history.publications[0],
        cursor_signing_key=key,
        cursor_verification_key=TrustedTypedValueArtifactVerificationKey(key.public_key().public_bytes_raw()),
        reader_limits=limits, correlation_token_factory=lambda: "correlation",
        retention_budget=ObservationRetentionBudget(
            maximum_stream_records=10, maximum_snapshot_bytes=100_000,
            maximum_retained_snapshots=10, maximum_retained_bytes=1_000_000,
            maximum_tenant_snapshots=10, maximum_tenant_bytes=1_000_000,
        ),
    )
    request = GraphObservationRequest(
        scope_constraint=MemoryScope(user_id="user"),
        cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("source",), seed_operation_ids=(), include_referenced_boundary_entities=True,
        ), view="current", expected_graph_revision="graph", expected_observation_revision="observation",
        valid_at=None, system_as_of=now, total_page_size=1, cursor=None,
    )
    first = runtime.observe_graph(host_ingress="trusted", request=request)
    assert isinstance(first, GraphObservationPage) and first.next_cursor is not None
    assert calls == ["context", "authorize", "cohort"]
    continuation = request.model_copy(update={"cursor": first.next_cursor})
    changed_request = continuation.model_copy(update={"expected_observation_revision": "other"})
    assert runtime.observe_graph(host_ingress="trusted", request=changed_request).reason == "invalid_cursor"
    calls.clear()
    second = runtime.observe_graph(host_ingress="trusted", request=continuation)
    assert isinstance(second, GraphObservationPage) and second.next_cursor is None
    assert [item.primary_key for item in (*first.records, *second.records)] == ["entity-1", "entity-2"]
    assert calls == ["context", "authorize"]
    denied = True
    calls.clear()
    assert runtime.observe_graph(host_ingress="trusted", request=continuation.model_copy(update={"cursor": "malformed"})).reason == "revoked_access"
    assert calls == ["context", "authorize"]
    denied = False
    plane.write_records((CanonicalMemoryRecord(
        memory_id="unrelated", domain=MemoryDomain.EXECUTION, text="write", content={},
        status=CommitStatus.COMMITTED, source_kind="test", timestamp=now,
    ),))
    assert runtime.observe_graph(host_ingress="trusted", request=continuation).reason == "stale_cursor"
    wrong_revision = True
    with pytest.raises(GraphObservationPagingError, match="cohort input coordinates"):
        runtime.observe_graph(host_ingress="trusted", request=request)


def test_observed_projection_records_page_with_publication_pairs(tmp_path, monkeypatch):
    """Projection records emitted by the producer page end to end.

    The fixture cohort collaborator returns the producer's real records for a
    retained two-generation projection history and fills the cohort preimage's
    projection publication pairs and boundary keys; the paging runtime
    re-verifies the derived identities and pages both records through one
    cursor continuation.  The legacy control (null pairs, no projection
    records) keeps its historical shape.
    """
    from tests.unit.core.memory_evolution.test_graph_observation_native_projection import (
        _PROJECTION_ROOTS,
        _project_publications,
        _published_history,
    )
    from tests.unit.core.test_projection_history import T0 as HISTORY_T0

    history, limits = observation_publication(tmp_path, monkeypatch, (
        *_PROJECTION_ROOTS, "AuthenticatedGraphObservationContext",
        "GraphObservationAuthorizationDecision", "GraphObservationPagePolicySnapshot",
        "GraphObservationCohortPreimage", "ResolvedGraphObservationCohort",
        "GraphRecordObservationSnapshot", "GraphObservationPage",
        "GraphObservationCursorPayload",
    ))
    publication = history.publications[0]
    harness, detached_repository = _published_history(
        tmp_path, monkeypatch, publications=2,
    )
    selection = _project_publications(
        (history, limits), detached_repository,
    )
    assert {item.record_kind for item in selection.records} == {
        "temporal_claim_projection", "trust_claim_projection",
    }

    def emit(value):
        return emit_registered_observation_artifact(
            value, schema_id=type(value).__name__, history=history,
            publication=publication, limits=limits,
        ).value

    now = datetime(2026, 9, 8, tzinfo=UTC)
    context = emit(AuthenticatedGraphObservationContext(
        principal_subject_id="principal", tenant_partition_id="tenant",
        authorized_scope_set_digest="a" * 64, authentication_session_id="session",
        context_digest="0" * 64,
    ))
    policy = emit(GraphObservationPagePolicySnapshot(
        policy_revision="page-policy", minimum_total_page_size=1, maximum_total_page_size=10,
        cursor_schema_version=1, snapshot_maximum_age=timedelta(minutes=5), policy_digest="0" * 64,
    ))
    decision = emit(GraphObservationAuthorizationDecision(
        kind="authorized", authorized_scope_identity="scope", policy_revision="policy",
        page_policy_revision=policy.policy_revision, page_policy_digest=policy.policy_digest,
        expires_at=now + timedelta(minutes=10), decision_digest="0" * 64,
    ))

    class Authority:
        def now(self):
            return now

        def resolve(self, **kwargs):
            return context

        def authorize(self, **kwargs):
            return VerifiedGraphObservationAuthorization(
                decision=decision, page_policy=policy, authorized_scope=MemoryScope(user_id="user"),
            )

        def graph_observation_input(self, *, snapshot, **kwargs):
            stream = selection.records
            boundary_keys = tuple(GraphObservationRecordKey(
                record_kind=item.record_kind, primary_key=item.primary_key,
            ) for item in stream)
            preimage = _cohorts()[0].model_copy(update={
                "memory_plane_write_revision": snapshot.memory_plane_write_revision,
                "authorization_decision_digest": decision.decision_digest,
                "changed_record_keys": (),
                "boundary_record_keys": boundary_keys,
                "temporal_projection_generation_digest": selection.temporal_generation_digest,
                "temporal_projection_pointer_digest": selection.temporal_pointer_digest,
                "trust_projection_generation_digest": selection.trust_generation_digest,
                "trust_projection_pointer_digest": selection.trust_pointer_digest,
            })
            return GraphObservationCohortInput(preimage, stream)

    key = Ed25519PrivateKey.generate()
    runtime = AuthenticatedGraphObservationPagingRuntime(
        memory_plane=MemoryPlaneService(), context_resolver=Authority(),
        authorizer=Authority(), cohort_provider=Authority(), protected_clock=Authority(),
        registry_history=history, registry_publication=publication,
        cursor_signing_key=key,
        cursor_verification_key=TrustedTypedValueArtifactVerificationKey(key.public_key().public_bytes_raw()),
        reader_limits=limits, correlation_token_factory=lambda: "correlation",
        retention_budget=ObservationRetentionBudget(
            maximum_stream_records=10, maximum_snapshot_bytes=200_000,
            maximum_retained_snapshots=10, maximum_retained_bytes=1_000_000,
            maximum_tenant_snapshots=10, maximum_tenant_bytes=1_000_000,
        ),
    )
    request = GraphObservationRequest(
        scope_constraint=MemoryScope(user_id="user"),
        cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("source",), seed_operation_ids=(),
            include_referenced_boundary_entities=True,
        ), view="current", expected_graph_revision="graph", expected_observation_revision="observation",
        valid_at=None, system_as_of=now, total_page_size=1, cursor=None,
    )
    first = runtime.observe_graph(host_ingress="trusted", request=request)
    assert isinstance(first, GraphObservationPage) and first.next_cursor is not None
    continuation = request.model_copy(update={"cursor": first.next_cursor})
    second = runtime.observe_graph(host_ingress="trusted", request=continuation)
    assert isinstance(second, GraphObservationPage) and second.next_cursor is None
    assert [item.record_kind for item in (*first.records, *second.records)] == [
        "temporal_claim_projection", "trust_claim_projection",
    ]
    cohort = first.cohort
    assert cohort.temporal_projection_generation_digest == (
        selection.temporal_generation_digest
    )
    assert cohort.temporal_projection_pointer_digest == selection.temporal_pointer_digest
    assert cohort.trust_projection_generation_digest == (
        selection.trust_generation_digest
    )
    assert cohort.trust_projection_pointer_digest == selection.trust_pointer_digest
    assert tuple(
        (item.record_kind, item.primary_key) for item in cohort.boundary_record_keys
    ) == tuple(
        (item.record_kind, item.primary_key) for item in selection.records
    )

    # Historical request coordinates page the historical selection the same
    # way, binding view/valid_at/system_as_of into the continuation.
    historical_selection = _project_publications(
        (history, limits), detached_repository, view="historical",
        valid_at=HISTORY_T0 + timedelta(minutes=30),
        system_as_of=HISTORY_T0 + timedelta(hours=1, minutes=30),
    )

    class HistoricalAuthority(Authority):
        def graph_observation_input(self, *, snapshot, **kwargs):
            stream = historical_selection.records
            preimage = _cohorts()[0].model_copy(update={
                "memory_plane_write_revision": snapshot.memory_plane_write_revision,
                "authorization_decision_digest": decision.decision_digest,
                "changed_record_keys": (),
                "boundary_record_keys": tuple(GraphObservationRecordKey(
                    record_kind=item.record_kind, primary_key=item.primary_key,
                ) for item in stream),
                "temporal_projection_generation_digest": historical_selection.temporal_generation_digest,
                "temporal_projection_pointer_digest": historical_selection.temporal_pointer_digest,
                "trust_projection_generation_digest": historical_selection.trust_generation_digest,
                "trust_projection_pointer_digest": historical_selection.trust_pointer_digest,
            })
            return GraphObservationCohortInput(preimage, stream)

    historical_runtime = AuthenticatedGraphObservationPagingRuntime(
        memory_plane=MemoryPlaneService(), context_resolver=HistoricalAuthority(),
        authorizer=HistoricalAuthority(), cohort_provider=HistoricalAuthority(),
        protected_clock=HistoricalAuthority(),
        registry_history=history, registry_publication=publication,
        cursor_signing_key=key,
        cursor_verification_key=TrustedTypedValueArtifactVerificationKey(key.public_key().public_bytes_raw()),
        reader_limits=limits, correlation_token_factory=lambda: "correlation",
        retention_budget=ObservationRetentionBudget(
            maximum_stream_records=10, maximum_snapshot_bytes=200_000,
            maximum_retained_snapshots=10, maximum_retained_bytes=1_000_000,
            maximum_tenant_snapshots=10, maximum_tenant_bytes=1_000_000,
        ),
    )
    historical_request = request.model_copy(update={
        "view": "historical", "valid_at": HISTORY_T0 + timedelta(minutes=30),
        "system_as_of": HISTORY_T0 + timedelta(hours=1, minutes=30),
    })
    historical_page = historical_runtime.observe_graph(
        host_ingress="trusted", request=historical_request,
    )
    assert isinstance(historical_page, GraphObservationPage)
    assert [item.record_kind for item in historical_page.records] == [
        "temporal_claim_projection",
    ]
    assert historical_page.records[0].payload.publication_pointer.pointer_digest == (
        historical_selection.temporal_pointer_digest
    )

    # Legacy control: a cohort without retained projection publications keeps
    # null pairs and pages without projection records.
    class LegacyAuthority(Authority):
        def graph_observation_input(self, *, snapshot, **kwargs):
            stream = ()
            preimage = _cohorts()[0].model_copy(update={
                "memory_plane_write_revision": snapshot.memory_plane_write_revision,
                "authorization_decision_digest": decision.decision_digest,
            })
            return GraphObservationCohortInput(preimage, stream)

    legacy_runtime = AuthenticatedGraphObservationPagingRuntime(
        memory_plane=MemoryPlaneService(), context_resolver=LegacyAuthority(),
        authorizer=LegacyAuthority(), cohort_provider=LegacyAuthority(),
        protected_clock=LegacyAuthority(),
        registry_history=history, registry_publication=publication,
        cursor_signing_key=key,
        cursor_verification_key=TrustedTypedValueArtifactVerificationKey(key.public_key().public_bytes_raw()),
        reader_limits=limits, correlation_token_factory=lambda: "correlation",
        retention_budget=ObservationRetentionBudget(
            maximum_stream_records=10, maximum_snapshot_bytes=200_000,
            maximum_retained_snapshots=10, maximum_retained_bytes=1_000_000,
            maximum_tenant_snapshots=10, maximum_tenant_bytes=1_000_000,
        ),
    )
    legacy_page = legacy_runtime.observe_graph(host_ingress="trusted", request=request)
    assert isinstance(legacy_page, GraphObservationPage)
    assert legacy_page.records == ()
    assert legacy_page.cohort.temporal_projection_generation_digest is None
    assert legacy_page.cohort.trust_projection_pointer_digest is None
