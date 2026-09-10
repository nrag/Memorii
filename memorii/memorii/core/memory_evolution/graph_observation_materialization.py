"""Detached cohort materialization for the public graph-observation runtime.

The provider deliberately obtains all semantic authority from the exact record
tuple supplied by paging plus the detached observation authority that tuple
reconstructs.  It has no memory-plane read path of its own.  Ingestion
observation records and graph mutation records are materialized separately and
merged into one complete stream; a partial or duplicated cohort is denied.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from memorii.core.memory_evolution.atomic_store import (
    DetachedSemanticObservationAuthority,
    SemanticIngestionAtomicStore,
)
from memorii.core.memory_evolution.graph_effect_contracts import (
    CanonicalIngestionObservationRecord,
    IngestionObservationDelta,
)
from memorii.core.memory_evolution.graph_observation_cohort import (
    ResolvedObservationMembership,
    resolve_observation_membership,
)
from memorii.core.memory_evolution.graph_observation_ingestion_projection import (
    materialize_ingestion_observation_stream,
)
from memorii.core.memory_evolution.graph_observation_native_projection import (
    NativeGraphObservationProjectionError,
    NativeGraphObservationStreamRecord,
    project_native_graph_observation_stream,
)
from memorii.core.memory_evolution.graph_observation_paging import (
    DetachedGraphObservationRecords,
    GraphObservationCohortInput,
    IngestionTimeObservationCohortInput,
    ObservationCohortUnavailableError,
)
from memorii.core.memory_evolution.graph_observation_public_contracts import (
    AuthenticatedGraphObservationContext,
    GraphObservationAuthorizationDecision,
    GraphObservationRequestCoordinates,
    IngestionTimeAttestationRequestCoordinates,
)
from memorii.core.memory_evolution.graph_observation_records import ObservedEntityReference
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationRecordKey,
)
from memorii.core.memory_evolution.graph_observation_streams import GraphObservationStreamRecord
from memorii.core.memory_evolution.graph_planning import (
    PlanningCommitValues,
    materialize_canonical_planning_payload,
)
from memorii.core.memory_evolution.graph_records import (
    CitationRecord,
    EntityRevision,
    ProvenanceRecord,
    graph_record_id,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_publication import VerifiedTypedValuePublication
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativeActionStateEffectV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeEvidenceProjectionV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeIdentityEffectV3,
    BootstrapNativeRetractionEffectV3,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_effect_contracts import GraphRevisionDelta
    from memorii.core.memory_evolution.graph_observation_streams import (
        OperationIntroductionStreamRecord,
        OperationTerminalOutcomeStreamRecord,
        SourceIntroductionStreamRecord,
        SourceTerminalOutcomeStreamRecord,
    )
    from memorii.core.semantic_ingestion.contracts import (
        BootstrapGraphGroupCommitRequestV3,
        BootstrapGraphOperationStoreMaterializationInputV3,
        BootstrapNativeAcceptedOperationEffectV3,
        BootstrapNativeOperationCompilationV3,
    )

    IngestionObservationStreamRecord: TypeAlias = (
        SourceIntroductionStreamRecord
        | OperationIntroductionStreamRecord
        | OperationTerminalOutcomeStreamRecord
        | SourceTerminalOutcomeStreamRecord
    )


class AtomicStoreGraphObservationCohortProvider:
    """Build a cohort from one replay-verified detached atomic-store image.

    Ingestion observation records are emitted from the retained ledger
    mutations.  Every selected accepted graph mutation is additionally
    projected through the registered native projection owner using the
    retained group request, its committed event-batch time, and the verified
    graph mutation inventory.  Returning a subset is forbidden: the paging
    runtime turns this provider's typed failures into its non-disclosing
    denial response.
    """

    def __init__(
        self, *, atomic_store: SemanticIngestionAtomicStore,
        registry_history: ProtectedTypedValueRegistryHistory,
        registry_publication: VerifiedTypedValuePublication,
        limits: ProtectedTypedValueArtifactReaderLimits,
    ) -> None:
        self._atomic_store = atomic_store
        self._history = registry_history
        self._publication = registry_publication
        self._limits = limits

    def graph_observation_input(
        self, *, snapshot: DetachedGraphObservationRecords,
        context: AuthenticatedGraphObservationContext,
        decision: GraphObservationAuthorizationDecision, authorized_scope: MemoryScope,
        request: GraphObservationRequestCoordinates, maximum_stream_records: int,
        maximum_snapshot_bytes: int,
    ) -> GraphObservationCohortInput:
        authority, membership = self._membership(snapshot, context, authorized_scope, request)
        ingestion = materialize_ingestion_observation_stream(
            membership=membership,
            records=self._ingestion_records(membership), history=self._history,
            publication=self._publication, limits=self._limits,
        )
        native = self._native_projection_records(
            authority=authority, membership=membership, snapshot=snapshot,
        )
        stream = _merge_observation_streams(ingestion, native)
        if len(stream) > maximum_stream_records:
            raise ObservationCohortUnavailableError("observation stream record ceiling exceeded")
        preimage = self._preimage(authority, membership, decision, request, stream)
        return GraphObservationCohortInput(cohort_preimage=preimage, stream=stream)

    def ingestion_time_input(
        self, *, snapshot: DetachedGraphObservationRecords,
        context: AuthenticatedGraphObservationContext,
        decision: GraphObservationAuthorizationDecision, authorized_scope: MemoryScope,
        request: IngestionTimeAttestationRequestCoordinates, maximum_stream_records: int,
        maximum_snapshot_bytes: int,
    ) -> IngestionTimeObservationCohortInput:
        # Persisted attestation authority is not present in the detached image's
        # public contract yet.  Do not synthesize a time witness from timestamps.
        raise ObservationCohortUnavailableError("persisted ingestion-time attestations are unavailable")

    def _membership(
        self, snapshot: DetachedGraphObservationRecords,
        context: AuthenticatedGraphObservationContext, authorized_scope: MemoryScope,
        request: GraphObservationRequestCoordinates,
    ) -> tuple[DetachedSemanticObservationAuthority, ResolvedObservationMembership]:
        authority = self._atomic_store.read_detached_observation_authority(
            write_revision=snapshot.memory_plane_write_revision, records=snapshot.records,
            snapshot_created_at=snapshot.created_at,
        )
        if authority.graph.graph_revision != request.expected_graph_revision:
            raise ObservationCohortUnavailableError("graph revision differs from request")
        if authority.observation.head.observation_revision != request.expected_observation_revision:
            raise ObservationCohortUnavailableError("observation revision differs from request")
        return authority, resolve_observation_membership(
            authority, context, authorized_scope, request.cohort_selector,
        )

    def _native_projection_records(
        self, *, authority: DetachedSemanticObservationAuthority,
        membership: ResolvedObservationMembership,
        snapshot: DetachedGraphObservationRecords,
    ) -> tuple[GraphObservationStreamRecord, ...]:
        """Project every selected accepted graph mutation exactly once."""
        if not membership.graph_deltas:
            return ()
        requests: dict[str, list[BootstrapGraphGroupCommitRequestV3]] = {}
        for group_request in authority.group_requests:
            requests.setdefault(group_request.transaction_group_id, []).append(group_request)
        system_interval = TimeInterval(start=snapshot.created_at)
        emitted: list[GraphObservationStreamRecord] = []
        for delta in membership.graph_deltas:
            matches = requests.get(delta.transaction_group_id, ())
            if len(matches) != 1:
                raise ObservationCohortUnavailableError(
                    "retained group request for a selected graph mutation is not unique"
                )
            request = matches[0]
            if (request.operation_ids != delta.operation_ids
                    or not set(delta.operation_ids).issubset(membership.operation_ids)):
                raise ObservationCohortUnavailableError(
                    "retained group request does not close the selected graph mutation"
                )
            commit_values = _commit_values(authority=authority, delta=delta)
            for item in request.ordered_operation_inputs:
                if item.reduction.native_terminal.status != "accepted":
                    continue
                projected = self._project_operation(
                    item=item, request=request, delta=delta, authority=authority,
                    commit_values=commit_values, system_interval=system_interval,
                )
                emitted.extend(projected)
        return tuple(emitted)

    def _project_operation(
        self, *, item: BootstrapGraphOperationStoreMaterializationInputV3,
        request: BootstrapGraphGroupCommitRequestV3, delta: GraphRevisionDelta,
        authority: DetachedSemanticObservationAuthority,
        commit_values: PlanningCommitValues, system_interval: TimeInterval,
    ) -> tuple[NativeGraphObservationStreamRecord, ...]:
        compilation: BootstrapNativeOperationCompilationV3 = (
            item.reduction.native_compilation
        )
        effect: BootstrapNativeAcceptedOperationEffectV3 | None = (
            item.reduction.effect_materialization.accepted_effect
        )
        intents = item.reduction.effect_materialization.record_intents
        if effect is None or not intents:
            raise ObservationCohortUnavailableError(
                "accepted graph mutation lacks its retained accepted effect or intents"
            )
        changes = {
            (change.record_kind, change.record_id): change
            for change in delta.record_changes
        }
        if len(changes) != len(delta.record_changes):
            raise ObservationCohortUnavailableError(
                "retained graph mutation has duplicate record identities"
            )
        materialized = []
        for intent in intents:
            record = materialize_canonical_planning_payload(
                intent.canonical_after_record, commit_values=commit_values,
                authorizing_transaction_group_id=request.transaction_group_id,
            )
            identity = (record.record_kind, graph_record_id(record))
            change = changes.get(identity)
            if ((intent.record_kind, intent.record_id) != identity
                    or change is None or change.after_digest != record.record_digest):
                raise ObservationCohortUnavailableError(
                    "accepted graph mutation is not the retained committed inventory"
                )
            materialized.append(record)
        evidence_pairs = []
        for projection in _accepted_evidence_projections(effect):
            citation = materialize_canonical_planning_payload(
                projection.citation_record.planning_payload, commit_values=commit_values,
                authorizing_transaction_group_id=request.transaction_group_id,
            )
            provenance = materialize_canonical_planning_payload(
                projection.provenance_record.planning_payload, commit_values=commit_values,
                authorizing_transaction_group_id=request.transaction_group_id,
            )
            if not isinstance(citation, CitationRecord) or not isinstance(provenance, ProvenanceRecord):
                raise ObservationCohortUnavailableError(
                    "retained evidence pair does not materialize to its canonical records"
                )
            evidence_pairs.append((citation, provenance))
        lookup = _native_entity_lookup(
            operation_records=tuple(materialized), authority=authority,
        )
        # Every projected native record is a changed record of a selected delta;
        # referenced-but-unchanged entities enter only through the lookup, so
        # the cohort boundary key set remains empty by construction.
        try:
            return project_native_graph_observation_stream(
                compilation=compilation,
                accepted_effect=effect,
                retained_native_records=tuple(materialized),
                evidence_pairs=tuple(evidence_pairs),
                commit_values=commit_values,
                authorizing_transaction_group_id=request.transaction_group_id,
                native_entity_lookup=lookup,
                boundary_ids=frozenset(),
                system_interval=system_interval,
                history=self._history,
                publication=self._publication,
                limits=self._limits,
            )
        except NativeGraphObservationProjectionError as exc:
            raise ObservationCohortUnavailableError(
                f"graph mutation projection is unavailable: {exc}"
            ) from exc

    @staticmethod
    def _ingestion_records(
        membership: ResolvedObservationMembership,
    ) -> tuple[CanonicalIngestionObservationRecord, ...]:
        records = [
            mutation.record
            for entry in membership.group_entries
            if isinstance(entry.delta, IngestionObservationDelta)
            for mutation in entry.delta.record_mutations
        ]
        records.extend(delta.source_outcome for delta in membership.source_finalizations)
        return tuple(records)

    @staticmethod
    def _preimage(
        authority: DetachedSemanticObservationAuthority,
        membership: ResolvedObservationMembership,
        decision: GraphObservationAuthorizationDecision,
        request: GraphObservationRequestCoordinates,
        stream: tuple[GraphObservationStreamRecord, ...],
    ) -> GraphObservationCohortPreimage:
        reference = authority.references
        certificate = reference.audit_certificate
        if certificate is None:
            raise ObservationCohortUnavailableError("reference audit certificate is unavailable")
        keys = tuple(GraphObservationRecordKey(record_kind=item.record_kind, primary_key=item.primary_key) for item in stream)
        return GraphObservationCohortPreimage(
            seed_source_ids=membership.seed_source_ids, seed_operation_ids=membership.seed_operation_ids,
            source_ids=membership.source_ids, operation_ids=membership.operation_ids,
            operation_fence_ids=membership.operation_fence_ids, include_referenced_boundary_entities=True,
            authorized_scope_identity=decision.authorized_scope_identity,
            authorization_policy_revision=decision.policy_revision,
            authorization_decision_digest=decision.decision_digest,
            graph_revision_delta_ids=tuple(delta.graph_revision_delta_id for delta in membership.graph_deltas),
            graph_revision_delta_digests=tuple(delta.delta_digest for delta in membership.graph_deltas),
            ingestion_observation_delta_ids=tuple(entry.delta.observation_delta_id for entry in membership.group_entries) + tuple(delta.observation_delta_id for delta in membership.source_finalizations),
            ingestion_observation_delta_digests=tuple(entry.delta.delta_digest for entry in membership.group_entries) + tuple(delta.delta_digest for delta in membership.source_finalizations),
            reference_schema_manifest_fingerprint=reference.manifest_fingerprint,
            reference_ledger_high_watermark=reference.high_watermark, reference_ledger_digest=reference.ledger_digest,
            reference_audit_certificate_digest=certificate.certificate_digest, complete=True,
            graph_revision=authority.graph.graph_revision, observation_revision=authority.observation.head.observation_revision,
            memory_plane_write_revision=authority.write_revision,
            temporal_projection_generation_digest=None, temporal_projection_pointer_digest=None,
            trust_projection_generation_digest=None, trust_projection_pointer_digest=None,
            observation_schema_fingerprint=_observation_schema_fingerprint(membership),
            changed_record_keys=keys, boundary_record_keys=(),
        )


def _accepted_evidence_projections(
    effect: BootstrapNativeAcceptedOperationEffectV3,
) -> tuple[BootstrapNativeEvidenceProjectionV3, ...]:
    """Select the exact retained evidence projections of each accepted arm.

    The correction arm retains its evidence projections on the replacement
    fact effect; every other accepted arm retains them directly.  This mirrors
    the projection owner's own arm dispatch without inventing a new selection.
    """
    if isinstance(effect, BootstrapNativeFactEffectV3):
        return effect.evidence_projections
    if isinstance(effect, BootstrapNativeCorrectionEffectV3):
        return effect.replacement_effect.evidence_projections
    if isinstance(
        effect,
        (BootstrapNativeRetractionEffectV3, BootstrapNativeActionStateEffectV3, BootstrapNativeIdentityEffectV3),
    ):
        return effect.evidence_projections
    raise ObservationCohortUnavailableError(
        "accepted operation arm has no exact observed projection recipe"
    )


def _commit_values(
    *, authority: DetachedSemanticObservationAuthority, delta: GraphRevisionDelta,
) -> PlanningCommitValues:
    """Bind the exact retained commit-event time of one graph mutation.

    The committed event batch is joined by its verified transaction group and
    must exactly close the delta's committed record inventory; its first event
    timestamp is the writer's committed coordinate.  No clock is sampled and no
    timestamp is guessed.
    """
    batches = tuple(
        batch for batch in authority.event_batches
        if batch.transaction_group_id == delta.transaction_group_id
    )
    if len(batches) != 1 or not batches[0].events:
        raise ObservationCohortUnavailableError(
            "committed graph mutation lacks its unique retained event batch"
        )
    events = {
        (event.payload.record_kind, event.payload.record_id): event.payload
        for event in batches[0].events
    }
    changes = {
        (change.record_kind, change.record_id): change
        for change in delta.record_changes
    }
    if (len(events) != len(batches[0].events)
            or len(changes) != len(delta.record_changes)
            or set(events) != set(changes)
            or any(
                change.after_digest != events[key].entity.record.record_digest
                for key, change in changes.items()
            )):
        raise ObservationCohortUnavailableError(
            "committed graph mutation differs from its retained event batch"
        )
    return PlanningCommitValues(
        transaction_group_id=delta.transaction_group_id,
        graph_revision_before=delta.graph_revision_before,
        graph_revision_after=delta.graph_revision_after,
        committed_at=batches[0].events[0].timestamp,
    )


def _native_entity_lookup(
    *, operation_records: tuple[object, ...], authority: DetachedSemanticObservationAuthority,
) -> dict[str, ObservedEntityReference]:
    """Resolve referenced entities from retained verified entity authority."""
    lookup: dict[str, ObservedEntityReference] = {}

    def add(record: EntityRevision) -> None:
        prior = lookup.get(record.entity_revision_id)
        if prior is not None and prior.logical_entity_id != record.logical_entity_id:
            raise ObservationCohortUnavailableError("retained entity authority is ambiguous")
        lookup[record.entity_revision_id] = ObservedEntityReference(
            entity_revision_id=record.entity_revision_id,
            logical_entity_id=record.logical_entity_id,
            reference_path="entity_revision_id",
        )

    for record in operation_records:
        if isinstance(record, EntityRevision):
            add(record)
    for snapshot_record in authority.graph.records:
        payload = snapshot_record.payload
        if isinstance(payload, EntityRevision):
            add(payload)
    return lookup


def _merge_observation_streams(
    ingestion: tuple[IngestionObservationStreamRecord, ...],
    native: tuple[GraphObservationStreamRecord, ...],
) -> tuple[GraphObservationStreamRecord, ...]:
    """Merge both sources into one sorted stream without duplicate identities."""
    merged: list[GraphObservationStreamRecord] = []
    identities: set[tuple[str, str]] = set()
    for source in (ingestion, native):
        for record in source:
            identity = (record.record_kind, record.primary_key)
            if identity in identities:
                raise ObservationCohortUnavailableError(
                    "merged observation stream has duplicate record identity"
                )
            identities.add(identity)
            merged.append(record)
    return tuple(sorted(merged, key=lambda item: (item.record_kind, item.primary_key)))


def _observation_schema_fingerprint(membership: ResolvedObservationMembership) -> str:
    """Require one exact schema binding across the selected ledger closure."""
    values = {entry.delta.observation_schema_fingerprint for entry in membership.group_entries}
    values.update(delta.observation_schema_fingerprint for delta in membership.source_finalizations)
    if len(values) != 1:
        raise ObservationCohortUnavailableError("selected observation deltas lack one schema fingerprint")
    return next(iter(values))


__all__ = ["AtomicStoreGraphObservationCohortProvider"]
