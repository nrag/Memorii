"""Service-configured end-to-end proof for the host-composed observation route.

One real activated atomic-store backend (no fixture cohort) is composed the
way a host must compose it: ``build_host_graph_observation_runtime`` binds
the protected paging runtime to the writer's exact store, registry history
and activation target, and ``ProviderMemoryService`` receives that runtime
through the factory pass-through.  ``observe_graph`` must then return real
registered pages and cursors over the committed ingestion conversion, and
``observe_ingestion_time_attestations`` must return real sealed attestation
pages (with signed continuations) resolved from the same store's minted
seals.
"""

from __future__ import annotations

import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution.graph_effect_contracts import (
    IngestionObservationDelta,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationCohortSelector
from memorii.core.memory_evolution.graph_observation_host import (
    ProtectedGraphObservationConfiguration,
    build_host_graph_observation_runtime,
)
from memorii.core.memory_evolution.graph_observation_paging import (
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
    attestation_order_key,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import (
    emit_registered_observation_artifact,
)
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    TrustedTypedValueArtifactVerificationKey,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from tests.integration.test_observation_ledger_activation import (
    _provider_factory,
    _seed_provider,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
    _host_ingress,
)

# The writer clock is frozen at TEST_NOW, so every detached read the paging
# runtime performs uses exactly this creation time as well.
_SNAPSHOT_TIME = TEST_NOW
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_INGESTION_KINDS = frozenset({
    "source_introduction", "operation_introduction",
    "operation_terminal_outcome", "source_terminal_outcome",
})
_NATIVE_KINDS = frozenset({
    "entity_revision", "claim_assertion", "relation", "citation", "provenance",
})
_FAILURE_FIELDS = {"kind", "reason", "request_correlation_token"}
_MAXIMUM_PAGES = 32


class _FixedContextResolver:
    """Host identity resolution reduced to the one authenticated test caller."""

    def __init__(self, context: AuthenticatedGraphObservationContext) -> None:
        self._context = context

    def resolve(self, *, host_ingress: object, server_time: object):
        del host_ingress, server_time
        return self._context


class _GrantingAuthorizer:
    """Host access policy granting both observation purposes to one scope."""

    def __init__(
        self,
        decision: GraphObservationAuthorizationDecision,
        policy: GraphObservationPagePolicySnapshot,
        scope: MemoryScope,
    ) -> None:
        self._decision = decision
        self._policy = policy
        self._scope = scope

    def authorize(self, *, context: object, scope_constraint: MemoryScope,
                  cohort_selector: object, purpose: str, server_time: object):
        del context, cohort_selector, server_time
        if (purpose not in {"graph_observation", "ingestion_time_attestation"}
                or not self._scope.can_read(scope_constraint)):
            return None
        return VerifiedGraphObservationAuthorization(
            decision=self._decision, page_policy=self._policy, authorized_scope=self._scope,
        )


def _unexpected_plane_read(*args: object, **kwargs: object) -> None:
    raise AssertionError("observation denial read the memory plane")


def _assert_non_disclosing_failure(response, reason: str) -> None:
    assert response.kind == "failure"
    assert response.reason == reason
    assert set(response.model_dump()) == _FAILURE_FIELDS


@pytest.fixture(scope="module")
def backend(tmp_path_factory, request):
    """One activated provider, its host-composed observation runtime and service."""
    patch = pytest.MonkeyPatch()
    # The store re-verifies its installed activation target on every detached
    # read, so the isolated package metadata must stay patched until the last
    # test of this module finished; only then is it restored.
    request.addfinalizer(patch.undo)
    tmp_path = tmp_path_factory.mktemp("composed-observation")
    build, _, clock = _provider_factory(
        tmp_path, patch, normalization=True, complete_registry=True,
    )
    plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(tmp_path / "ledger-store"))
    writer = build(plane)
    _seed_provider(writer)
    writer.activate_observation_ledger()
    result = writer.sync_event(
        operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
        operation_id="composed-source", task_id="task:one", user_id="user:alice",
        authenticated_host_ingress=_host_ingress(),
    )
    assert result is not None
    semantic = writer._composed_semantic_runtime
    assert (
        semantic is not None
        and semantic.atomic_store is not None
        and semantic.typed_value_registry_history is not None
        and semantic.observation_activation_target is not None
    )
    # The detached authority head supplies the exact revisions a caller must pin.
    write_revision, records = plane.read_write_snapshot()
    authority = semantic.atomic_store.read_detached_observation_authority(
        write_revision=write_revision, records=records,
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
    grant = MemoryScope(user_id="user:alice", task_id="task:one")

    def emit(value):
        # Registered authority models must be emitted through the writer's
        # registry before use: emission recomputes their self-digest fields,
        # and the paging runtime re-emits and compares them on every request.
        return emit_registered_observation_artifact(
            value, schema_id=type(value).__name__,
            history=semantic.typed_value_registry_history,
            publication=semantic.observation_activation_target.publication,
            limits=semantic.atomic_store._observation_artifact_limits,
        ).value

    context = emit(AuthenticatedGraphObservationContext(
        principal_subject_id="user:alice",
        tenant_partition_id=finalization.delta.required_outcome_scopes.tenant_partition_id,
        authorized_scope_set_digest="a" * 64, authentication_session_id="composed-session",
        context_digest="b" * 64,
    ))
    policy = emit(GraphObservationPagePolicySnapshot(
        policy_revision="composed-page-policy", minimum_total_page_size=1,
        maximum_total_page_size=100, cursor_schema_version=1,
        snapshot_maximum_age=timedelta(minutes=5), policy_digest="0" * 64,
    ))
    decision = emit(GraphObservationAuthorizationDecision(
        kind="authorized", authorized_scope_identity="composed-scope",
        policy_revision="composed-policy", page_policy_revision=policy.policy_revision,
        page_policy_digest=policy.policy_digest,
        expires_at=_SNAPSHOT_TIME + timedelta(hours=1), decision_digest="c" * 64,
    ))
    key = Ed25519PrivateKey.generate()
    observation_runtime = build_host_graph_observation_runtime(
        configuration=ProtectedGraphObservationConfiguration(
            context_resolver=_FixedContextResolver(context),
            authorizer=_GrantingAuthorizer(decision, policy, grant),
            cursor_signing_key=key,
            cursor_verification_key=TrustedTypedValueArtifactVerificationKey(
                key.public_key().public_bytes_raw(),
            ),
            reader_limits=semantic.atomic_store._observation_artifact_limits,
            retention_budget=ObservationRetentionBudget(
                maximum_stream_records=1000, maximum_snapshot_bytes=10_000_000,
                maximum_retained_snapshots=10, maximum_retained_bytes=40_000_000,
                maximum_tenant_snapshots=10, maximum_tenant_bytes=40_000_000,
            ),
        ),
        memory_plane=plane,
        atomic_store=semantic.atomic_store,
        registry_history=semantic.typed_value_registry_history,
        activation_target=semantic.observation_activation_target,
        now_provider=lambda: clock[0],
    )
    service = build_provider_memory_service_from_env(
        memory_plane=plane, now_provider=lambda: clock[0],
        graph_observation_runtime=observation_runtime,
    )
    selector = GraphObservationCohortSelector(
        seed_source_ids=(group_entry.delta.source_id,),
        seed_operation_ids=(), include_referenced_boundary_entities=True,
    )
    graph_request = GraphObservationRequest(
        scope_constraint=grant, cohort_selector=selector, view="current",
        expected_graph_revision=authority.graph.graph_revision,
        expected_observation_revision=authority.observation.head.observation_revision,
        valid_at=None, system_as_of=_SNAPSHOT_TIME, total_page_size=3, cursor=None,
    )
    time_request = IngestionTimeAttestationRequest(
        scope_constraint=grant, cohort_selector=selector,
        expected_graph_revision=authority.graph.graph_revision,
        expected_observation_revision=authority.observation.head.observation_revision,
        total_page_size=3, cursor=None,
    )
    return SimpleNamespace(
        service=service, plane=plane, graph_request=graph_request,
        time_request=time_request, grant=grant, clock=clock,
        write_revision=write_revision,
        graph_revision=authority.graph.graph_revision,
        observation_revision=authority.observation.head.observation_revision,
    )


def test_configured_service_observe_graph_returns_real_page(backend):
    first = backend.service.observe_graph(
        host_ingress=_host_ingress(), request=backend.graph_request,
    )
    assert isinstance(first, GraphObservationPage)
    assert first.kind == "page"
    assert set(first.model_dump()) == set(GraphObservationPage.model_fields)
    assert first.graph_revision == backend.graph_revision
    assert first.observation_revision == backend.observation_revision
    assert first.memory_plane_write_revision == backend.write_revision
    assert first.snapshot_token
    assert first.page_policy_revision == "composed-page-policy"
    assert first.view == "current" and first.valid_at is None
    assert first.system_as_of == _SNAPSHOT_TIME
    assert first.cohort.seed_source_ids == backend.graph_request.cohort_selector.seed_source_ids
    assert 0 < len(first.records) <= first.total_page_size == 3
    assert (first.stream_start_position, first.stream_end_position) == (0, len(first.records))
    # The committed cohort is strictly longer than one page, so a real
    # signed continuation cursor must be issued.
    assert first.next_cursor is not None
    records = list(first.records)
    cursor = first.next_cursor
    expected_start = first.stream_end_position
    pages = 1
    while cursor is not None:
        assert pages < _MAXIMUM_PAGES
        page = backend.service.observe_graph(
            host_ingress=_host_ingress(),
            request=backend.graph_request.model_copy(update={"cursor": cursor}),
        )
        assert isinstance(page, GraphObservationPage)
        assert page.kind == "page"
        assert page.stream_start_position == expected_start
        assert 0 < len(page.records) <= page.total_page_size
        assert page.stream_end_position == expected_start + len(page.records)
        records.extend(page.records)
        expected_start = page.stream_end_position
        cursor = page.next_cursor
        pages += 1
    identities = [(item.record_kind, item.primary_key) for item in records]
    assert identities == sorted(set(identities))
    kinds = {item.record_kind for item in records}
    assert kinds >= _INGESTION_KINDS
    assert kinds >= _NATIVE_KINDS
    for record in records:
        assert _HEX64.fullmatch(record.record_digest)
        assert record.record_digest != "0" * 64
        assert record.record_digest == record.payload.record_digest
    # The final page releases the retained snapshot, so the exhausted
    # continuation cursor is stale by the paging runtime contract.
    exhausted = backend.service.observe_graph(
        host_ingress=_host_ingress(),
        request=backend.graph_request.model_copy(update={"cursor": first.next_cursor}),
    )
    _assert_non_disclosing_failure(exhausted, "stale_cursor")


def test_configured_service_observe_ingestion_time_attestations_returns_real_page(backend):
    """The sealed store pages its minted attestations end to end.

    Page size one forces a real signed continuation; the cursor carries the
    exact predecessor triple (kind, id, digest) of the attestation it
    follows, the concatenated pages stay in the registered order-key order,
    and every artifact names the store's composed clock identity.
    """
    paged = backend.time_request.model_copy(update={"total_page_size": 1})
    first = backend.service.observe_ingestion_time_attestations(
        host_ingress=_host_ingress(), request=paged,
    )
    assert isinstance(first, IngestionTimeAttestationPage)
    assert first.kind == "page"
    assert set(first.model_dump()) == set(IngestionTimeAttestationPage.model_fields)
    assert first.graph_revision == backend.graph_revision
    assert first.observation_revision == backend.observation_revision
    assert first.memory_plane_write_revision == backend.write_revision
    assert first.page_policy_revision == "composed-page-policy"
    assert 0 < len(first.attestations) <= first.total_page_size == 1
    assert (first.stream_start_position, first.stream_end_position) == (
        0, len(first.attestations),
    )
    runtime = backend.service._graph_observation_runtime
    attestations = list(first.attestations)
    cursor = first.next_cursor
    if cursor is not None:
        payload = runtime._decode_ingestion_cursor(cursor)
        assert payload is not None
        predecessor = attestations[-1]
        assert payload.stream_position == first.stream_end_position
        assert (
            payload.preceding_attestation_kind,
            payload.preceding_attestation_id,
            payload.preceding_attestation_digest,
        ) == (
            predecessor.kind, predecessor.attestation_id,
            predecessor.attestation_digest,
        )
    expected_start = first.stream_end_position
    pages = 1
    while cursor is not None:
        assert pages < _MAXIMUM_PAGES
        page = backend.service.observe_ingestion_time_attestations(
            host_ingress=_host_ingress(),
            request=paged.model_copy(update={"cursor": cursor}),
        )
        assert isinstance(page, IngestionTimeAttestationPage)
        assert page.kind == "page"
        assert page.stream_start_position == expected_start
        assert 0 < len(page.attestations) <= page.total_page_size
        assert page.stream_end_position == expected_start + len(page.attestations)
        attestations.extend(page.attestations)
        expected_start = page.stream_end_position
        cursor = page.next_cursor
        pages += 1
    keys = [attestation_order_key(item) for item in attestations]
    assert keys == sorted(set(keys))
    assert {item.kind for item in attestations} == {
        "source_retention", "transaction_group_commit",
    }
    clock_identity = (
        runtime._cohort_provider._atomic_store.ingestion_time_seal_reader_authority()[2]
    )
    for item in attestations:
        assert item.clock_identity == clock_identity
        assert _HEX64.fullmatch(item.attestation_digest)
        assert item.attestation_digest != "0" * 64
    # The final page releases the retained snapshot, so replaying the first
    # continuation cursor is stale by the paging runtime contract.
    if first.next_cursor is not None:
        exhausted = backend.service.observe_ingestion_time_attestations(
            host_ingress=_host_ingress(),
            request=paged.model_copy(update={"cursor": first.next_cursor}),
        )
        _assert_non_disclosing_failure(exhausted, "stale_cursor")


def test_unconfigured_and_misconfigured_fail_closed(backend, monkeypatch):
    unconfigured = build_provider_memory_service_from_env()
    monkeypatch.setattr(unconfigured._memory_plane, "read_write_snapshot", _unexpected_plane_read)
    monkeypatch.setattr(
        unconfigured._memory_plane, "read_timed_write_snapshot", _unexpected_plane_read,
    )
    ingress = _host_ingress()
    selector = GraphObservationCohortSelector(
        seed_source_ids=("unknown",), seed_operation_ids=(),
        include_referenced_boundary_entities=True,
    )
    coordinates = dict(
        scope_constraint=MemoryScope(user_id="alice"), cohort_selector=selector,
        expected_graph_revision="graph", expected_observation_revision="observation",
    )
    graph_request = GraphObservationRequest(
        **coordinates, view="current", valid_at=None, system_as_of=_SNAPSHOT_TIME,
        total_page_size=1, cursor=None,
    )
    time_request = IngestionTimeAttestationRequest(**coordinates, total_page_size=1, cursor=None)
    responses = [
        unconfigured.observe_graph(host_ingress=ingress, request=graph_request),
        unconfigured.observe_graph(
            host_ingress=ingress,
            request=graph_request.model_copy(update={"cursor": "untrusted-token"}),
        ),
        unconfigured.observe_ingestion_time_attestations(host_ingress=ingress, request=time_request),
        unconfigured.observe_ingestion_time_attestations(
            host_ingress=ingress,
            request=time_request.model_copy(update={"cursor": "untrusted-token"}),
        ),
    ]
    expected = ["denied", "revoked_access", "denied", "revoked_access"]
    tokens = set()
    for response, reason in zip(responses, expected, strict=True):
        _assert_non_disclosing_failure(response, reason)
        tokens.add(response.request_correlation_token)
    assert len(tokens) == len(responses)
    # With the runtime configured, an unresolvable cohort (an unknown seed) is
    # still the non-disclosing denial decided by the cohort provider.
    unknown_seed = IngestionTimeAttestationRequest(
        scope_constraint=MemoryScope(user_id="alice"),
        cohort_selector=GraphObservationCohortSelector(
            seed_source_ids=("unknown",), seed_operation_ids=(),
            include_referenced_boundary_entities=True,
        ),
        expected_graph_revision=backend.graph_revision,
        expected_observation_revision=backend.observation_revision,
        total_page_size=1, cursor=None,
    )
    denial = backend.service.observe_ingestion_time_attestations(
        host_ingress=ingress, request=unknown_seed,
    )
    _assert_non_disclosing_failure(denial, "denied")


def test_cross_purpose_cursor_denied(backend, monkeypatch):
    first = backend.service.observe_graph(
        host_ingress=_host_ingress(), request=backend.graph_request,
    )
    assert isinstance(first, GraphObservationPage)
    assert first.next_cursor is not None
    cross_purpose = IngestionTimeAttestationRequest(
        scope_constraint=backend.grant,
        cohort_selector=backend.graph_request.cohort_selector,
        expected_graph_revision=backend.graph_revision,
        expected_observation_revision=backend.observation_revision,
        total_page_size=backend.graph_request.total_page_size,
        cursor=first.next_cursor,
    )
    # The cross-purpose denial is decided at cursor decode, before any
    # snapshot read on the continuation path.
    monkeypatch.setattr(backend.plane, "read_write_snapshot", _unexpected_plane_read)
    monkeypatch.setattr(backend.plane, "read_timed_write_snapshot", _unexpected_plane_read)
    response = backend.service.observe_ingestion_time_attestations(
        host_ingress=_host_ingress(), request=cross_purpose,
    )
    _assert_non_disclosing_failure(response, "invalid_cursor")

