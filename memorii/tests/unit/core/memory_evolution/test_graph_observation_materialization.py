"""Focused proof for the detached cohort materialization provider.

The provider is exercised directly against the real activated atomic-store
backend reused from the detached-cohort integration harness: two committed
fact sources (the second retained separately from the first), one detached
observation authority, and one merged observation stream containing both
ingestion records and native projection records with real registered digests.
System intervals are asserted against the commit-event time, never the
snapshot time.  No fixture cohort stands in for the backend.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.atomic_store import (
    _group_commit_seal_member_id,
    _source_retention_seal_member_id,
)
from memorii.core.memory_evolution.graph_effect_contracts import (
    IngestionObservationDelta,
    SourceFinalizationObservationDelta,
)
from memorii.core.memory_evolution.graph_ingestion_time_contracts import (
    SourceRetentionTimeAttestation,
    TransactionGroupCommitTimeAttestation,
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
    _attestation_order_key,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationRecordKey,
)
from memorii.core.memory_evolution.graph_records import EntityRevision
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore, record_digest
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.provider.models import ProviderOperation
from pydantic import ValidationError
from tests.integration.test_observation_ledger_activation import (
    _provider_factory,
    _seed_provider,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
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
    """One real activated provider with two committed fact sources.

    The second source is retained separately from the first: the current
    ingestion conversions allocate source-scoped entity identities, so no
    selected cohort gains a cross-transaction reference by itself.  The
    boundary-join tests below use the substituted-authority seam to construct
    exactly that reference; everything else runs on the real backend.
    """
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
    for operation_id in ("materialization-source", "materialization-source-2"):
        result = provider.sync_event(
            operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.",
            operation_id=operation_id, task_id="task:one", user_id="user:alice",
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
    selected_delta = next(
        delta for delta in authority.graph_deltas
        if delta.transaction_group_id == group_entry.delta.transaction_group_id
    )
    other_delta = next(
        delta for delta in authority.graph_deltas
        if delta is not selected_delta
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
        selected_delta=selected_delta, other_delta=other_delta,
        group_entry=group_entry, finalization_entry=finalization,
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


def _time_input(backend, **overrides):
    values = dict(
        snapshot=backend.snapshot,
        context=backend.context,
        decision=backend.decision,
        authorized_scope=backend.grant,
        request=backend.time_coordinates,
        maximum_stream_records=_MAXIMUM_STREAM_RECORDS,
        maximum_snapshot_bytes=_MAXIMUM_SNAPSHOT_BYTES,
    )
    values.update(overrides)
    return backend.provider.ingestion_time_input(**values)


def _substitute_authority(backend, monkeypatch, **substitutions):
    """Serve one model_copy-substituted authority image to the provider.

    The paging runtime re-verifies every substituted field through the
    provider's integrity joins; the seam only constructs joins the current
    ingestion conversions cannot produce.  Pydantic ``model_copy`` skips
    contract revalidation, so tampered images reach the guards unvalidated
    exactly as a corrupted store image would.  Every call rebinds to the
    pristine reader so repeated substitutions within one test never stack.
    """
    atomic_store = backend.provider._atomic_store
    pristine = type(atomic_store).read_detached_observation_authority.__get__(atomic_store)

    def read_detached_observation_authority(**kwargs):
        return dataclasses.replace(pristine(**kwargs), **substitutions)

    monkeypatch.setattr(
        atomic_store,
        "read_detached_observation_authority",
        read_detached_observation_authority,
    )


def _selected_batch(backend):
    return next(
        batch for batch in backend.authority.event_batches
        if batch.transaction_group_id == backend.selected_delta.transaction_group_id
    )


def _other_batch(backend):
    return next(
        batch for batch in backend.authority.event_batches
        if batch.transaction_group_id == backend.other_delta.transaction_group_id
    )


def _entity_event(batch):
    return next(
        event for event in batch.events
        if event.payload.record_kind == "entity_revision"
    )


def _boundary_edge(delta):
    """One real retained entity-revision reference edge of a relation change."""
    relation = next(
        change for change in delta.record_changes
        if change.record_kind == "relation_revision"
    )
    return next(
        edge for edge in relation.reference_edges_added
        if edge.target.kind == "entity_revision"
    )


def _fabricated_successor(event, *, timestamp, digest):
    return event.model_copy(update={
        "timestamp": timestamp,
        "payload": event.payload.model_copy(update={
            "operation": "update",
            "record_digest": digest,
            "prior_record_digest": event.payload.record_digest,
            "metadata": event.payload.metadata.model_copy(update={"version": 2}),
        }),
    })


def test_merged_stream_contains_ingestion_and_native_records(backend):
    cohort = _cohort_input(backend)
    kinds = [item.record_kind for item in cohort.stream]
    identities = [(item.record_kind, item.primary_key) for item in cohort.stream]
    assert kinds == sorted(kinds)
    assert len(identities) == len(set(identities))
    assert set(kinds) >= _INGESTION_KINDS
    assert set(kinds) >= _NATIVE_KINDS
    projection_kinds = ("temporal_claim_projection", "trust_claim_projection")
    changed = [
        item for item in cohort.stream if item.record_kind not in projection_kinds
    ]
    projections = [
        item for item in cohort.stream if item.record_kind in projection_kinds
    ]
    for record in cohort.stream:
        assert _HEX64.fullmatch(record.record_digest)
        assert record.record_digest != "0" * 64
        assert record.record_digest == record.payload.record_digest
        if "system_interval" in type(record.payload).model_fields:
            # System intervals are the retained commit-event time (the frozen
            # writer clock), never the snapshot creation time.
            assert record.payload.system_interval == TimeInterval(start=TEST_NOW)
            assert record.payload.system_interval != TimeInterval(start=_SNAPSHOT_TIME)
        if "boundary" in type(record.payload).model_fields:
            # Projection publications are boundary records: retained state
            # selected through their own publication pointers, never changes
            # of the selected deltas.  Every other record of this real
            # single-delta cohort is changed by the delta itself.
            assert record.payload.boundary is (record.record_kind in projection_kinds)
    claim = next(item for item in cohort.stream if item.record_kind == "claim_assertion")
    assert claim.payload.polarity == "positive"
    assert claim.payload.policy_fingerprints == tuple(sorted(set(claim.payload.policy_fingerprints)))
    assert claim.payload.subject_assertion_ref.entity.reference_path == (
        "/claim_identity/subject_assertion_ref/entity_revision_id"
    )
    assert claim.payload.object_assertion_ref is not None
    assert claim.payload.object_assertion_ref.entity.reference_path == (
        "/claim_identity/object_assertion_ref/entity_revision_id"
    )
    relation = next(item for item in cohort.stream if item.record_kind == "relation")
    assert relation.payload.subject.reference_path == "subject_entity_revision_id"
    assert relation.payload.object_entity.reference_path == "object_entity_revision_id"
    preimage = cohort.cohort_preimage
    assert preimage.changed_record_keys == tuple(
        GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key)
        for item in changed
    )
    # Projection publications, when the detached image retains them, are the
    # cohort's boundary records and name their selected generation/pointer
    # pairs; a history absent before the first publication keeps null pairs.
    assert preimage.boundary_record_keys == tuple(
        GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key)
        for item in projections
    )
    assert (preimage.temporal_projection_generation_digest is None) == (
        "temporal_claim_projection" not in kinds
    )
    assert (preimage.temporal_projection_pointer_digest is None) == (
        "temporal_claim_projection" not in kinds
    )
    assert (preimage.trust_projection_generation_digest is None) == (
        "trust_claim_projection" not in kinds
    )
    assert (preimage.trust_projection_pointer_digest is None) == (
        "trust_claim_projection" not in kinds
    )
    if projections:
        active_temporal = backend.authority.projection_history.active_temporal_authority()
        active_trust = backend.authority.projection_history.active_trust_authority()
        assert preimage.temporal_projection_generation_digest == (
            active_temporal.pointer.generation_digest
        )
        assert preimage.temporal_projection_pointer_digest == (
            active_temporal.pointer.pointer_digest
        )
        assert preimage.trust_projection_generation_digest == (
            active_trust.pointer.generation_digest
        )
        assert preimage.trust_projection_pointer_digest == (
            active_trust.pointer.pointer_digest
        )
        for item in projections:
            payload = item.payload
            assert payload.boundary is True
            assert payload.successor_publication_pointer is None
            assert item.primary_key == payload.observation_id
    assert len(preimage.graph_revision_delta_ids) == 1
    assert preimage.graph_revision_delta_digests == (backend.selected_delta.delta_digest,)
    assert preimage.graph_revision == backend.authority.graph.graph_revision
    assert preimage.observation_revision == backend.authority.observation.head.observation_revision
    assert preimage.memory_plane_write_revision == backend.snapshot.memory_plane_write_revision
    assert preimage.authorization_decision_digest == backend.decision.decision_digest
    assert preimage.authorized_scope_identity == backend.decision.authorized_scope_identity


def test_identical_authority_at_different_snapshot_times_is_deterministic(backend):
    """The determinism property: observation depends on the retained event
    authority, not the wall-clock snapshot time."""
    first = _cohort_input(backend)
    later = _cohort_input(
        backend,
        snapshot=dataclasses.replace(
            backend.snapshot, created_at=_SNAPSHOT_TIME + timedelta(days=365),
        ),
        request=backend.coordinates.model_copy(update={
            "system_as_of": _SNAPSHOT_TIME + timedelta(days=365),
        }),
    )
    assert [(item.record_kind, item.primary_key) for item in later.stream] == [
        (item.record_kind, item.primary_key) for item in first.stream
    ]
    assert [item.record_digest for item in later.stream] == [
        item.record_digest for item in first.stream
    ]
    assert later.cohort_preimage == first.cohort_preimage


def test_cross_transaction_referenced_entity_emits_boundary_record(backend, monkeypatch):
    """A referenced-but-unchanged entity revision becomes a boundary record.

    The current ingestion conversions allocate source-scoped entities, so the
    cross-transaction reference is constructed through the substituted
    authority seam: the selected delta's relation gains one real retained
    reference edge of the other transaction.  The boundary payload must then
    derive from the other transaction's own retained record and events.
    """
    other_edge = _boundary_edge(backend.other_delta)
    boundary_entity_id = other_edge.target.target_id
    selected_relation = next(
        change for change in backend.selected_delta.record_changes
        if change.record_kind == "relation_revision"
    )
    tampered_changes = tuple(
        change.model_copy(update={
            "reference_edges_added": (*change.reference_edges_added, other_edge),
        })
        if change is selected_relation else change
        for change in backend.selected_delta.record_changes
    )
    selected = backend.selected_delta.model_copy(update={"record_changes": tampered_changes})
    _substitute_authority(backend, monkeypatch, graph_deltas=tuple(
        selected if delta is backend.selected_delta else delta
        for delta in backend.authority.graph_deltas
    ))
    cohort = _cohort_input(backend)
    boundary = [
        item for item in cohort.stream
        if item.record_kind == "entity_revision" and item.payload.boundary
    ]
    assert [item.primary_key for item in boundary] == [boundary_entity_id]
    payload = boundary[0].payload
    assert _HEX64.fullmatch(payload.record_digest)
    assert boundary[0].record_digest == payload.record_digest
    assert payload.logical_entity_id
    assert payload.canonical_type is None
    assert payload.valid_interval is None
    # The boundary interval is the other transaction's own commit-event time.
    assert payload.system_interval == TimeInterval(start=TEST_NOW)
    retained = next(
        record.payload for record in backend.authority.graph.records
        if isinstance(record.payload, EntityRevision)
        and record.payload.entity_revision_id == boundary_entity_id
    )
    # Source ids are the record's own lineage only, never this operation's.
    assert payload.source_ids == tuple(sorted({
        item.source_id for item in retained.source_evidence
    }))
    assert payload.operation_ids == (retained.operation_id,)
    preimage = cohort.cohort_preimage
    projection_kinds = ("temporal_claim_projection", "trust_claim_projection")
    projections = [
        item for item in cohort.stream if item.record_kind in projection_kinds
    ]
    # Boundary keys carry the referenced entity plus the separately selected
    # projection publications, never a change of the selected deltas.
    assert preimage.boundary_record_keys == (
        GraphObservationRecordKey(record_kind="entity_revision", primary_key=boundary_entity_id),
        *(
            GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key)
            for item in projections
        ),
    )
    assert all(
        (item.record_kind, item.primary_key) != ("entity_revision", boundary_entity_id)
        for item in preimage.changed_record_keys
    )
    assert tuple(
        GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key)
        for item in cohort.stream if not (
            item.record_kind == "entity_revision" and item.payload.boundary
        ) and item.record_kind not in projection_kinds
    ) == preimage.changed_record_keys


def test_boundary_entity_without_retained_owning_event_denies(backend, monkeypatch):
    """A boundary entity whose owning commit event is not retained denies."""
    other_edge = _boundary_edge(backend.other_delta)
    boundary_entity_id = other_edge.target.target_id
    tampered_changes = tuple(
        change.model_copy(update={
            "reference_edges_added": (*change.reference_edges_added, other_edge),
        })
        if change.record_kind == "relation_revision" else change
        for change in backend.selected_delta.record_changes
    )
    selected = backend.selected_delta.model_copy(update={"record_changes": tampered_changes})
    other_batch = _other_batch(backend)
    stripped = other_batch.model_copy(update={
        "events": tuple(
            event for event in other_batch.events
            if not (
                event.payload.record_kind == "entity_revision"
                and event.payload.record_id == boundary_entity_id
            )
        ),
    })
    _substitute_authority(
        backend, monkeypatch,
        graph_deltas=tuple(
            selected if delta is backend.selected_delta else delta
            for delta in backend.authority.graph_deltas
        ),
        event_batches=tuple(
            stripped if batch is other_batch else batch
            for batch in backend.authority.event_batches
        ),
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="boundary entity revision has no unique retained owning commit event",
    ):
        _cohort_input(backend)


def test_event_derived_interval_successor_rules(backend, monkeypatch):
    """Successor events drive interval ends; ambiguity and disorder deny."""
    batch = _selected_batch(backend)
    other_batch = _other_batch(backend)
    entity_event = _entity_event(batch)
    later = _fabricated_successor(
        entity_event, timestamp=TEST_NOW + timedelta(seconds=1), digest="e" * 64,
    )
    _substitute_authority(backend, monkeypatch, event_batches=tuple(
        other_batch.model_copy(update={"events": (*other_batch.events, later)})
        if item is other_batch else item
        for item in backend.authority.event_batches
    ))
    cohort = _cohort_input(backend)
    advanced = next(
        item.payload for item in cohort.stream
        if item.record_kind == "entity_revision"
        and item.primary_key == entity_event.payload.record_id
    )
    assert advanced.system_interval == TimeInterval(
        start=TEST_NOW, end=TEST_NOW + timedelta(seconds=1),
    )
    same_time = _fabricated_successor(entity_event, timestamp=TEST_NOW, digest="f" * 64)
    _substitute_authority(backend, monkeypatch, event_batches=tuple(
        other_batch.model_copy(update={"events": (*other_batch.events, same_time)})
        if item is other_batch else item
        for item in backend.authority.event_batches
    ))
    cohort = _cohort_input(backend)
    retained = next(
        item.payload for item in cohort.stream
        if item.record_kind == "entity_revision"
        and item.primary_key == entity_event.payload.record_id
    )
    # A same-time successor retains exact lineage with an unbounded end; no
    # positive interval is invented.
    assert retained.system_interval == TimeInterval(start=TEST_NOW)
    assert retained.system_interval.end is None
    earlier = _fabricated_successor(
        entity_event, timestamp=TEST_NOW - timedelta(seconds=1), digest="1" * 64,
    )
    _substitute_authority(backend, monkeypatch, event_batches=tuple(
        other_batch.model_copy(update={"events": (*other_batch.events, earlier)})
        if item is other_batch else item
        for item in backend.authority.event_batches
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="successor commit event is not ordered after its owning event",
    ):
        _cohort_input(backend)
    ambiguous = (
        _fabricated_successor(entity_event, timestamp=TEST_NOW + timedelta(seconds=1), digest="2" * 64),
        _fabricated_successor(entity_event, timestamp=TEST_NOW + timedelta(seconds=2), digest="3" * 64),
    )
    _substitute_authority(backend, monkeypatch, event_batches=tuple(
        other_batch.model_copy(update={"events": (*other_batch.events, *ambiguous)})
        if item is other_batch else item
        for item in backend.authority.event_batches
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="record version has ambiguous successor commit events",
    ):
        _cohort_input(backend)


def test_duplicate_group_request_denies(backend, monkeypatch):
    _substitute_authority(
        backend, monkeypatch,
        group_requests=(*backend.authority.group_requests, backend.authority.group_requests[0]),
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="retained group request for a selected graph mutation is not unique",
    ):
        _cohort_input(backend)


def test_missing_effect_or_intents_denies(backend, monkeypatch):
    group_request = next(
        request for request in backend.authority.group_requests
        if request.transaction_group_id == backend.selected_delta.transaction_group_id
    )
    item = group_request.ordered_operation_inputs[0]
    without_effect = item.model_copy(update={
        "reduction": item.reduction.model_copy(update={
            "effect_materialization": item.reduction.effect_materialization.model_copy(
                update={"accepted_effect": None},
            ),
        }),
    })
    _substitute_authority(backend, monkeypatch, group_requests=tuple(
        request.model_copy(update={"ordered_operation_inputs": (without_effect,)})
        if request is group_request else request
        for request in backend.authority.group_requests
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="accepted graph mutation lacks its retained accepted effect or intents",
    ):
        _cohort_input(backend)
    without_intents = item.model_copy(update={
        "reduction": item.reduction.model_copy(update={
            "effect_materialization": item.reduction.effect_materialization.model_copy(
                update={"record_intents": ()},
            ),
        }),
    })
    _substitute_authority(backend, monkeypatch, group_requests=tuple(
        request.model_copy(update={"ordered_operation_inputs": (without_intents,)})
        if request is group_request else request
        for request in backend.authority.group_requests
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="accepted graph mutation lacks its retained accepted effect or intents",
    ):
        _cohort_input(backend)


def test_intent_inventory_mismatch_denies(backend, monkeypatch):
    group_request = next(
        request for request in backend.authority.group_requests
        if request.transaction_group_id == backend.selected_delta.transaction_group_id
    )
    item = group_request.ordered_operation_inputs[0]
    intents = item.reduction.effect_materialization.record_intents
    tampered = intents[0].model_copy(update={"record_id": "tampered:record:id"})
    substituted = item.model_copy(update={
        "reduction": item.reduction.model_copy(update={
            "effect_materialization": item.reduction.effect_materialization.model_copy(
                update={"record_intents": (tampered, *intents[1:])},
            ),
        }),
    })
    _substitute_authority(backend, monkeypatch, group_requests=tuple(
        request.model_copy(update={"ordered_operation_inputs": (substituted,)})
        if request is group_request else request
        for request in backend.authority.group_requests
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="accepted graph mutation is not the retained committed inventory",
    ):
        _cohort_input(backend)


def test_evidence_pair_outside_committed_inventory_denies(backend, monkeypatch):
    """An accepted effect's evidence pair whose citation record is not a
    committed record of the selected delta denies."""
    group_request = next(
        request for request in backend.authority.group_requests
        if request.transaction_group_id == backend.selected_delta.transaction_group_id
    )
    item = group_request.ordered_operation_inputs[0]
    effect = item.reduction.effect_materialization.accepted_effect
    projection = effect.evidence_projections[0]
    citation = projection.citation_record
    payload = citation.planning_payload.model_copy(deep=True)
    payload.planning_record["citation_id"] = "citation:uncommitted"
    tampered_pair = projection.model_copy(update={
        "citation_record": citation.model_copy(update={
            "record_id": "citation:uncommitted",
            "planning_payload": payload,
        }),
    })
    substituted_effect = effect.model_copy(update={
        "evidence_projections": (tampered_pair, *effect.evidence_projections[1:]),
    })
    substituted = item.model_copy(update={
        "reduction": item.reduction.model_copy(update={
            "effect_materialization": item.reduction.effect_materialization.model_copy(
                update={"accepted_effect": substituted_effect},
            ),
        }),
    })
    _substitute_authority(backend, monkeypatch, group_requests=tuple(
        request.model_copy(update={"ordered_operation_inputs": (substituted,)})
        if request is group_request else request
        for request in backend.authority.group_requests
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="accepted effect evidence pair is not part of the committed record inventory",
    ):
        _cohort_input(backend)


def test_change_without_accepted_intent_denies(backend, monkeypatch):
    """A committed record change covered by no accepted operation's record
    intents denies instead of being silently dropped.

    The uncovered change and its owning commit event are moved from the other
    transaction into the selected delta's changes and event batch, so every
    earlier integrity join (event-batch closure, commit coordinates, system
    intervals) still passes and only the group-level intent union denies.
    """
    other_change = next(
        change for change in backend.other_delta.record_changes
        if change.record_kind == "entity_revision"
    )
    other_batch = _other_batch(backend)
    other_event = next(
        event for event in other_batch.events
        if event.payload.record_kind == "entity_revision"
        and event.payload.record_id == other_change.record_id
    )
    selected_batch = _selected_batch(backend)
    selected = backend.selected_delta.model_copy(update={
        "record_changes": (*backend.selected_delta.record_changes, other_change),
    })
    moved_batches = []
    for batch in backend.authority.event_batches:
        if batch is selected_batch:
            moved_batches.append(batch.model_copy(update={
                "events": (*batch.events, other_event),
            }))
        elif batch is other_batch:
            moved_batches.append(batch.model_copy(update={
                "events": tuple(event for event in batch.events if event is not other_event),
            }))
        else:
            moved_batches.append(batch)
    _substitute_authority(
        backend, monkeypatch,
        graph_deltas=tuple(
            selected if delta is backend.selected_delta else delta
            for delta in backend.authority.graph_deltas
        ),
        event_batches=tuple(moved_batches),
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="committed graph mutation is not closed by the accepted operations' "
        "record intents",
    ):
        _cohort_input(backend)


def test_event_batch_record_set_mismatch_denies(backend, monkeypatch):
    batch = _selected_batch(backend)
    stripped = batch.model_copy(update={"events": batch.events[:-1]})
    _substitute_authority(backend, monkeypatch, event_batches=tuple(
        stripped if item is batch else item
        for item in backend.authority.event_batches
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="committed graph mutation differs from its retained event batch",
    ):
        _cohort_input(backend)


def test_stream_ceiling_exceeded_denies(backend):
    with pytest.raises(
        ObservationCohortUnavailableError, match="observation stream record ceiling exceeded",
    ):
        _cohort_input(backend, maximum_stream_records=1)


def test_missing_reference_audit_certificate_denies(backend, monkeypatch):
    _substitute_authority(
        backend, monkeypatch,
        references=backend.authority.references.model_copy(update={"audit_certificate": None}),
    )
    with pytest.raises(
        ObservationCohortUnavailableError, match="reference audit certificate is unavailable",
    ):
        _cohort_input(backend)


def test_ambiguous_retained_entity_authority_denies(backend, monkeypatch):
    graph = backend.authority.graph
    entity_id = _entity_event(_selected_batch(backend)).payload.record_id
    entity_record = next(
        record for record in graph.records
        if isinstance(record.payload, EntityRevision)
        and record.payload.entity_revision_id == entity_id
    )
    payload = entity_record.payload
    conflicting = entity_record.model_copy(update={
        "payload": payload.model_copy(update={"logical_entity_id": "logical:conflicting"}),
    })
    _substitute_authority(backend, monkeypatch, graph=graph.model_copy(update={
        "records": (*graph.records, conflicting),
    }))
    with pytest.raises(
        ObservationCohortUnavailableError, match="retained entity authority is ambiguous",
    ):
        _cohort_input(backend)


def test_duplicate_merged_identity_denies(backend):
    cohort = _cohort_input(backend)
    ingestion = tuple(
        item for item in cohort.stream if item.record_kind in _INGESTION_KINDS
    )
    native = tuple(
        item for item in cohort.stream if item.record_kind in _NATIVE_KINDS
    )
    projection_kinds = ("temporal_claim_projection", "trust_claim_projection")
    projections = tuple(
        item for item in cohort.stream if item.record_kind in projection_kinds
    )
    assert ingestion and native
    # The provider merges ingestion records, native delta records, boundary
    # entities, and separately selected projection publications.
    assert _merge_observation_streams(ingestion, (*native, *projections)) == cohort.stream
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


def test_ingestion_time_input_resolves_sealed_attestations(backend):
    """The sealed store's reader pages real attestations through verified joins.

    One selected sealed source yields its source-retention seal (bound to the
    retained record's own retention instant and complete record digest) and one
    transaction-group-commit seal per committed group (bound to the group's
    locator, operation set, applied delta digest and persisted batch digest),
    every artifact naming the store's composed clock identity, emitted exactly
    in the registered ``_attestation_order_key`` order.
    """
    cohort = _time_input(backend)
    attestations = cohort.stream
    assert attestations
    keys = [_attestation_order_key(item) for item in attestations]
    assert keys == sorted(set(keys))
    kinds = [item.kind for item in attestations]
    assert kinds == sorted(kinds)
    assert set(kinds) == {"source_retention", "transaction_group_commit"}
    clock_identity = backend.provider._atomic_store.ingestion_time_seal_reader_authority()[2]
    finalization = backend.finalization_entry.delta
    source_record = next(
        record for record in backend.snapshot.records
        if record.memory_id == finalization.source_id
    )
    source = next(item for item in attestations if item.kind == "source_retention")
    assert source.attestation_id == _source_retention_seal_member_id(
        finalization.delivery_key_digest
    )
    assert source.source_id == finalization.source_id
    assert source.operation_fence_id == finalization.operation_fence_id
    assert source.retained_at == source_record.timestamp
    assert source.source_record_digest == record_digest(source_record)
    assert source.attestation_digest == (
        finalization.source_outcome.source_retention_attestation_digest
    )
    assert source.clock_identity == clock_identity
    assert _HEX64.fullmatch(source.attestation_digest)
    assert source.attestation_digest != "0" * 64
    entry = backend.group_entry
    group = next(
        item for item in attestations
        if item.kind == "transaction_group_commit"
        and item.transaction_group_id == entry.delta.transaction_group_id
    )
    batch = next(
        batch for batch in backend.authority.event_batches
        if batch.transaction_group_id == entry.delta.transaction_group_id
    )
    assert group.attestation_id == _group_commit_seal_member_id(
        entry.result_locator.immutable_record_id
    )
    assert group.source_id == entry.delta.source_id
    assert group.operation_fence_id == entry.delta.operation_fence_id
    assert group.operation_ids == entry.delta.operation_ids
    assert group.applied_graph_delta_digest == batch.graph_delta_digest
    assert group.committed_batch_digest == batch.source_event_batch_digest
    assert group.clock_identity == clock_identity
    assert group.transaction_started_at <= group.transaction_committed_at
    assert _HEX64.fullmatch(group.attestation_digest)
    assert group.attestation_digest != "0" * 64
    preimage = cohort.cohort_preimage
    assert preimage.memory_plane_write_revision == backend.snapshot.memory_plane_write_revision
    assert preimage.graph_revision == backend.time_coordinates.expected_graph_revision
    assert preimage.observation_revision == (
        backend.time_coordinates.expected_observation_revision
    )
    assert preimage.authorization_decision_digest == backend.decision.decision_digest
    assert preimage.authorized_scope_identity == backend.decision.authorized_scope_identity
    assert preimage.authorization_policy_revision == backend.decision.policy_revision
    assert preimage.source_ids == (finalization.source_id,)
    assert preimage.seed_source_ids == backend.time_coordinates.cohort_selector.seed_source_ids
    # The ingestion-time stream carries attestations, not graph records, and
    # selects no projection publications.
    assert preimage.changed_record_keys == ()
    assert preimage.boundary_record_keys == ()
    assert preimage.temporal_projection_generation_digest is None
    assert preimage.temporal_projection_pointer_digest is None
    assert preimage.trust_projection_generation_digest is None
    assert preimage.trust_projection_pointer_digest is None
    assert _HEX64.fullmatch(preimage.observation_schema_fingerprint)


def test_ingestion_time_stream_ceiling_exceeded_denies(backend):
    with pytest.raises(
        ObservationCohortUnavailableError, match="observation stream record ceiling exceeded",
    ):
        _time_input(backend, maximum_stream_records=1)


def _legacy_finalization_entry(entry):
    """One finalization whose outcome bytes predate seals (schema 1)."""
    legacy_outcome = entry.delta.source_outcome.model_copy(update={
        "source_result_schema_version": 1,
        "source_retention_attestation_digest": None,
    })
    return entry.model_copy(update={
        "delta": entry.delta.model_copy(update={"source_outcome": legacy_outcome}),
    })


def test_ingestion_time_legacy_outcome_denies(backend, monkeypatch):
    """A cohort whose finalization predates seals is a typed denial."""
    entries = tuple(
        _legacy_finalization_entry(entry) if entry is backend.finalization_entry else entry
        for entry in backend.authority.observation.entries
    )
    _substitute_authority(
        backend, monkeypatch,
        observation=backend.authority.observation.model_copy(update={"entries": entries}),
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="legacy source finalization predates ingestion-time seals",
    ):
        _time_input(backend)


def test_ingestion_time_mixed_sealed_and_legacy_cohort_denies(backend, monkeypatch):
    """A cohort mixing one sealed and one legacy finalization denies whole."""
    finalizations = tuple(
        entry for entry in backend.authority.observation.entries
        if isinstance(entry.delta, SourceFinalizationObservationDelta)
    )
    assert len(finalizations) == 2
    other = next(entry for entry in finalizations if entry is not backend.finalization_entry)
    entries = tuple(
        _legacy_finalization_entry(entry) if entry is other else entry
        for entry in backend.authority.observation.entries
    )
    _substitute_authority(
        backend, monkeypatch,
        observation=backend.authority.observation.model_copy(update={"entries": entries}),
    )
    mixed_selector = GraphObservationCohortSelector(
        seed_source_ids=tuple(sorted({
            backend.finalization_entry.delta.source_id, other.delta.source_id,
        })),
        seed_operation_ids=(), include_referenced_boundary_entities=True,
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="legacy source finalization predates ingestion-time seals",
    ):
        _time_input(
            backend,
            request=backend.time_coordinates.model_copy(
                update={"cohort_selector": mixed_selector},
            ),
        )


def test_ingestion_time_legacy_group_core_denies(backend, monkeypatch):
    """A group result at core schema below 3 is a typed denial.

    The reload decode is downgraded to schema 1 at the reader's seam only:
    the retained primary bytes stay sealed, so exactly the reader's
    legacy-core guard can fire.
    """
    selector = GraphObservationCohortSelector(
        seed_source_ids=(), seed_operation_ids=backend.group_entry.delta.operation_ids,
        include_referenced_boundary_entities=True,
    )
    assert any(
        record.memory_id == backend.group_entry.result_locator.immutable_record_id
        for record in backend.snapshot.records
    )
    _seal_schema_override(backend, monkeypatch, group_schema=1)
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="legacy group result predates ingestion-time seals",
    ):
        _time_input(
            backend,
            request=backend.time_coordinates.model_copy(
                update={"cohort_selector": selector},
            ),
        )


def _seal_schema_override(backend, monkeypatch, *, group_schema):
    """Serve a schema-downgraded group reload decode to the reader only."""
    from memorii.core.memory_evolution import graph_observation_materialization as materialization
    from memorii.core.semantic_ingestion import contracts as semantic_contracts

    pristine = materialization.decode_semantic_contract

    def decode(raw, expected_type, **kwargs):
        value = pristine(raw, expected_type, **kwargs)
        if expected_type is semantic_contracts.BootstrapGraphGroupCommitReloadV3:
            core = value.persisted_result.core
            value = value.model_copy(update={
                "group_result_schema_version": group_schema,
                "persisted_result": value.persisted_result.model_copy(update={
                    "core": core.model_copy(update={
                        "group_result_schema_version": group_schema,
                        "transaction_group_commit_attestation_digest": None,
                    }),
                }),
            })
        return value

    monkeypatch.setattr(materialization, "decode_semantic_contract", decode)


def test_ingestion_time_absent_group_seal_member_denies(backend):
    """A tampered snapshot missing the group seal member denies the cohort."""
    member_id = _group_commit_seal_member_id(
        backend.group_entry.result_locator.immutable_record_id
    )
    stripped = dataclasses.replace(backend.snapshot, records=tuple(
        record for record in backend.snapshot.records if record.memory_id != member_id
    ))
    with pytest.raises(
        ObservationCohortUnavailableError, match="group commit seal member is absent",
    ):
        _time_input(backend, snapshot=stripped)


def test_ingestion_time_substituted_source_seal_member_denies(backend):
    """A tampered seal-member artifact fails its registered validation."""
    finalization = backend.finalization_entry.delta
    member_id = _source_retention_seal_member_id(finalization.delivery_key_digest)
    member = next(
        record for record in backend.snapshot.records if record.memory_id == member_id
    )
    artifact = member.content["artifact"]
    tampered = member.model_copy(update={"content": {
        **member.content, "artifact": artifact[:64] + "X" + artifact[65:],
    }})
    substituted = dataclasses.replace(backend.snapshot, records=tuple(
        tampered if record.memory_id == member_id else record
        for record in backend.snapshot.records
    ))
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="ingestion-time seal member is substituted",
    ):
        _time_input(backend, snapshot=substituted)


def test_ingestion_time_unsealed_store_denies(backend, monkeypatch):
    """A store without a seal publication is a typed denial, never a guess."""
    monkeypatch.setattr(
        backend.provider._atomic_store, "_ingestion_time_seal_authority", lambda: None,
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="ingestion-time seal publication is unavailable for this store",
    ):
        _time_input(backend)


def test_ingestion_time_empty_cohort_pages_empty(backend):
    """A cohort with no ingestion results at all is a valid empty stream.

    The closed selector contract requires seeds and the shared membership
    resolver requires every seed source to be terminal, so a genuinely empty
    resolved membership cannot be produced by a valid request.  The reader's
    own empty permission is therefore proven at the seams it owns: an empty
    membership pages an empty attestation stream and a preimage carrying the
    retained ledger activation's fingerprint, instead of denying emptiness.
    """
    from memorii.core.memory_evolution.graph_observation_cohort import (
        ResolvedObservationMembership,
    )
    from memorii.core.memory_evolution.graph_observation_materialization import (
        _ingestion_time_cohort_preimage,
        _sealed_ingestion_time_attestations,
    )

    empty_membership = ResolvedObservationMembership(
        seed_source_ids=("source:seed",), seed_operation_ids=(),
        source_ids=(), operation_ids=(), operation_fence_ids=(),
        source_finalizations=(), group_entries=(), graph_deltas=(),
    )
    attestations = _sealed_ingestion_time_attestations(
        atomic_store=backend.provider._atomic_store,
        reader_history=backend.provider._history,
        limits=backend.provider._limits,
        snapshot_records=backend.snapshot.records,
        authority=backend.authority,
        membership=empty_membership,
    )
    assert attestations == ()
    preimage = _ingestion_time_cohort_preimage(
        backend.authority, empty_membership, backend.decision,
        snapshot_records=backend.snapshot.records,
        history=backend.provider._history, limits=backend.provider._limits,
    )
    assert preimage.source_ids == ()
    assert preimage.operation_ids == ()
    assert preimage.graph_revision_delta_ids == ()
    assert preimage.ingestion_observation_delta_ids == ()
    assert preimage.changed_record_keys == ()
    activation = next(
        record for record in backend.snapshot.records
        if record.source_kind == "semantic_ingestion_observation_ledger_activation"
    )
    assert preimage.observation_schema_fingerprint == _activation_fingerprint(
        backend, activation,
    )
    # The same empty permission holds end to end at the page contract: an
    # empty attestation page is valid exactly at position zero with no
    # continuation, and nowhere else.
    from memorii.core.memory_evolution.graph_observation_public_contracts import (
        IngestionTimeAttestationPage,
    )
    from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
        ResolvedGraphObservationCohort,
    )

    empty_cohort = ResolvedGraphObservationCohort(
        **{**preimage.model_dump(mode="python"), "cohort_digest": "0" * 64},
    )
    page_common = dict(
        kind="page", graph_revision=preimage.graph_revision,
        observation_revision=preimage.observation_revision,
        snapshot_token="snapshot",
        memory_plane_write_revision=preimage.memory_plane_write_revision,
        cohort=empty_cohort,
        page_policy_revision="policy", page_policy_digest="0" * 64,
        total_page_size=1, page_digest="0" * 64,
    )
    assert IngestionTimeAttestationPage(
        **page_common, stream_start_position=0, stream_end_position=0,
        attestations=(), next_cursor=None,
    )
    for invalid in (
        {"stream_start_position": 1, "stream_end_position": 1, "attestations": (),
         "next_cursor": None},
        {"stream_start_position": 0, "stream_end_position": 0, "attestations": (),
         "next_cursor": "cursor"},
    ):
        with pytest.raises(ValidationError):
            IngestionTimeAttestationPage(**page_common, **invalid)


def _activation_fingerprint(backend, activation_record):
    from memorii.core.memory_evolution.observation_activation_runtime import (
        validate_registered_artifact,
    )

    value = validate_registered_artifact(
        activation_record.content["artifact"].encode("utf-8"),
        schema_id="ObservationLedgerActivation",
        history=backend.provider._history,
        limits=backend.provider._limits,
    )
    return value.observation_schema_fingerprint


def test_ingestion_time_order_key_contract():
    """Fast unit-tier proof of the registered attestation order key.

    Source seals sort before group seals by kind, the transaction-group slot
    is empty exactly for the source kind, and the attestation id is the final
    tie-break; the stream order the reader emits and the runtime enforces is
    exactly this key.  (The cursor predecessor-triple semantics are proven in
    test_graph_observation_public_contracts.py.)
    """
    source = SourceRetentionTimeAttestation(
        kind="source_retention", attestation_id="seal:a",
        source_id="source:1", operation_fence_id="fence:1",
        retained_at=TEST_NOW, graph_revision="g" * 8, clock_identity="clock:1",
        source_record_digest="1" * 64, attestation_digest="2" * 64,
    )
    group = TransactionGroupCommitTimeAttestation(
        kind="transaction_group_commit", attestation_id="seal:b",
        source_id="source:1", operation_fence_id="fence:1",
        transaction_group_id="group:2", operation_ids=("op:1",),
        transaction_started_at=TEST_NOW, transaction_committed_at=TEST_NOW,
        graph_revision_before="a" * 8, graph_revision_after="b" * 8,
        applied_graph_delta_digest="3" * 64, clock_identity="clock:1",
        committed_batch_digest="4" * 64, attestation_digest="5" * 64,
    )
    assert _attestation_order_key(source) == (
        "source_retention", "source:1", "fence:1", "", "seal:a",
    )
    assert _attestation_order_key(group) == (
        "transaction_group_commit", "source:1", "fence:1", "group:2", "seal:b",
    )
    assert _attestation_order_key(source) < _attestation_order_key(group)
    later_group = group.model_copy(update={"transaction_group_id": "group:3"})
    assert _attestation_order_key(group) < _attestation_order_key(later_group)
    later_fence = source.model_copy(update={"operation_fence_id": "fence:2"})
    assert _attestation_order_key(source) < _attestation_order_key(later_fence)
    later_id = source.model_copy(update={"attestation_id": "seal:z"})
    assert _attestation_order_key(source) < _attestation_order_key(later_id)


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
