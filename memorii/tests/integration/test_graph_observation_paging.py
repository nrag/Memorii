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
