"""Real registered authority emission from protected host grants."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from memorii.core.memory_evolution.graph_observation_access import (
    ProtectedObservationGrant,
    ProtectedObservationSession,
    RegisteredGraphObservationAccess,
)
from memorii.core.memory_evolution.graph_observation_contracts import (
    GraphObservationCohortSelector,
    authorized_scope_identity,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import GraphObservationPagePolicySnapshot
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress, RequiredOutcomeScopeSet
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import emit_registered_observation_artifact
from tests.fixtures.semantic_ingestion.observation_publication import observation_publication


def test_registered_access_rejects_substituted_and_expired_host_grants(tmp_path, monkeypatch):
    history, limits = observation_publication(tmp_path, monkeypatch, (
        "AuthenticatedGraphObservationContext", "GraphObservationAuthorizationDecision",
        "GraphObservationPagePolicySnapshot",
    ))
    now = datetime(2026, 9, 8, tzinfo=UTC)
    ingress = AuthenticatedHostIngress(
        provider_identity="host", principal_handle=object(), session_handle=object(), received_at=now,
    )
    session = ProtectedObservationSession(
        principal_subject_id="alice", authentication_session_id="session",
        authorized_scopes=RequiredOutcomeScopeSet.create(tenant_partition_id="tenant", scopes=("user:alice",)),
        issued_at=now, expires_at=now + timedelta(minutes=5),
    )
    policy = emit_registered_observation_artifact(
        GraphObservationPagePolicySnapshot(
            policy_revision="pages", minimum_total_page_size=1, maximum_total_page_size=10,
            cursor_schema_version=1, snapshot_maximum_age=timedelta(minutes=1), policy_digest="0" * 64,
        ), schema_id="GraphObservationPagePolicySnapshot", history=history,
        publication=history.publications[0], limits=limits,
    ).value
    grant = None

    class Grants:
        def resolve(self, **kwargs):
            return grant

    access = RegisteredGraphObservationAccess(
        session_provider=lambda handoff, instant: session if handoff is ingress else None,
        grant_provider=Grants(), registry_history=history,
        registry_publication=history.publications[0], reader_limits=limits,
    )
    context = access.resolve(host_ingress=ingress, server_time=now)
    assert context is not None and context.context_digest != "0" * 64
    assert context.authorized_scope_set_digest == session.authorized_scopes.required_scope_set_digest
    assert access.resolve(host_ingress="alice", server_time=now) is None
    assert access.resolve(host_ingress=ingress, server_time=session.expires_at) is None
    scope = MemoryScope(user_id="alice")
    selector = GraphObservationCohortSelector(
        seed_source_ids=("source",), seed_operation_ids=(), include_referenced_boundary_entities=True,
    )
    def authorize():
        return access.authorize(
            context=context, purpose="graph_observation", scope_constraint=scope,
            cohort_selector=selector, server_time=now,
        )
    assert authorize() is None
    grant = ProtectedObservationGrant(
        context=context, session=session, purpose="graph_observation", scope_constraint=scope,
        cohort_selector=selector, authorized_scope=scope, authorized_scope_identity=authorized_scope_identity(scope),
        authorization_policy_revision="access", page_policy=policy,
        issued_at=now, expires_at=session.expires_at,
    )
    authorized = authorize()
    assert authorized is not None and authorized.decision.decision_digest != "0" * 64
    assert authorized.authorized_scope == scope
    original = grant
    for mutation in (
        {"purpose": "ingestion_time_attestation"},
        {"context": context.model_copy(update={"authentication_session_id": "other"})},
        {"scope_constraint": MemoryScope(user_id="other")},
        {"authorized_scope": MemoryScope(user_id="other")},
        {"authorized_scope_identity": "substituted-scope"},
        {"cohort_selector": selector.model_copy(update={"seed_source_ids": ("other",)})},
        {"issued_at": now + timedelta(seconds=1)},
        {"expires_at": now},
        {"expires_at": session.expires_at + timedelta(seconds=1)},
        {"session": replace(session, authentication_session_id="other")},
        {"page_policy": policy.model_copy(update={"maximum_total_page_size": 11})},
    ):
        grant = replace(original, **mutation)
        assert authorize() is None, mutation
