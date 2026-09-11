"""Detached cohort materialization for the public graph-observation runtime.

The provider deliberately obtains all semantic authority from the exact record
tuple supplied by paging plus the detached observation authority that tuple
reconstructs.  It has no memory-plane read path of its own.  Ingestion
observation records and graph mutation records are materialized separately and
merged into one complete stream; a partial or duplicated cohort is denied.
Temporal and trust claim projections are exposed separately from their own
retained projection publications, selected by the requested view/time and
never derived from graph deltas.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Literal, TypeAlias, TypeVar

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
from memorii.core.memory_evolution.graph_observation_contracts import GraphObservationView
from memorii.core.memory_evolution.graph_observation_ingestion_projection import (
    materialize_ingestion_observation_stream,
)
from memorii.core.memory_evolution.graph_observation_native_projection import (
    NativeGraphObservationProjectionError,
    NativeGraphObservationStreamRecord,
    project_boundary_entity_revision,
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
from memorii.core.memory_evolution.graph_observation_records import (
    ObservedTemporalClaimProjection,
    ObservedTrustClaimProjection,
)
from memorii.core.memory_evolution.graph_observation_snapshot_contracts import (
    GraphObservationCohortPreimage,
    GraphObservationRecordKey,
)
from memorii.core.memory_evolution.graph_observation_streams import (
    GraphObservationStreamRecord,
    TemporalClaimProjectionStreamRecord,
    TrustClaimProjectionStreamRecord,
)
from memorii.core.memory_evolution.graph_planning import (
    PlanningCommitValues,
    materialize_canonical_planning_payload,
)
from memorii.core.memory_evolution.graph_records import (
    CitationRecord,
    EntityRevision,
    ProvenanceRecord,
    TypeEvidence,
    graph_record_id,
)
from memorii.core.memory_evolution.models import MemoryScope
from memorii.core.memory_evolution.observation_activation_runtime import (
    ObservationActivationRuntimeError,
    derive_projection_observation_identity,
    emit_registered_observation_artifact,
    projection_observation_identity_root_selected,
)
from memorii.core.memory_evolution.projection_history import (
    ProjectionHistoryError,
    ProjectionHistoryRepository,
)
from memorii.core.memory_evolution.semantic_state import (
    ActiveTemporalProjectionPointer,
    ActiveTrustProjectionPointer,
    TemporalProjectionRecord,
    TemporalProjectionView,
    TrustProjectionRecord,
    TrustProjectionView,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_evolution.typed_value_artifact_reader import ProtectedTypedValueArtifactReaderLimits
from memorii.core.memory_evolution.typed_value_model_codec import TypedValueModelCodecCapacityError
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
    from memorii.core.semantic_ingestion.event_replay import SemanticMemoryEvent

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
    retained group request, per-version commit-event-derived system intervals,
    and the verified graph mutation inventory.  Entity revisions referenced
    through a selected delta's reference edges but changed by no selected
    delta are emitted as boundary records from their own retained native
    authority.  Returning a subset is forbidden: the paging runtime turns this
    provider's typed failures into its non-disclosing denial response.
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
            authority=authority, membership=membership,
        )
        boundary = self._boundary_stream_records(authority=authority, membership=membership)
        projections = project_observed_claim_projections(
            projection_history=authority.projection_history,
            view=request.view, valid_at=request.valid_at,
            system_as_of=request.system_as_of,
            graph_revision=authority.graph.graph_revision,
            history=self._history, publication=self._publication, limits=self._limits,
        )
        stream = _merge_observation_streams(ingestion, (*native, *boundary, *projections.records))
        if len(stream) > maximum_stream_records:
            raise ObservationCohortUnavailableError("observation stream record ceiling exceeded")
        preimage = self._preimage(
            authority, membership, decision, request, (*ingestion, *native),
            (*boundary, *projections.records), projections,
        )
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
    ) -> tuple[GraphObservationStreamRecord, ...]:
        """Project every selected accepted graph mutation exactly once."""
        if not membership.graph_deltas:
            return ()
        requests: dict[str, list[BootstrapGraphGroupCommitRequestV3]] = {}
        for group_request in authority.group_requests:
            requests.setdefault(group_request.transaction_group_id, []).append(group_request)
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
            system_intervals = _event_derived_system_intervals(
                authority=authority,
                versions=tuple(
                    (change.record_kind, change.record_id, change.after_digest)
                    for change in delta.record_changes
                ),
            )
            covered: set[tuple[str, str]] = set()
            for item in request.ordered_operation_inputs:
                if item.reduction.native_terminal.status != "accepted":
                    continue
                projected = self._project_operation(
                    item=item, request=request, delta=delta, authority=authority,
                    commit_values=commit_values, system_intervals=system_intervals,
                    covered=covered,
                )
                emitted.extend(projected)
            # Converse of the per-operation intent joins: the union of every
            # accepted operation's record intents must close the whole group's
            # committed record changes.  Non-accepted operations carry no
            # intents or effects (the effect-materialization contract denies
            # "nonaccepting native materialization has effects"), so a change
            # covered by no accepted intent is unobserved by anything and
            # denies instead of being silently dropped.
            uncovered = sorted(
                {(change.record_kind, change.record_id) for change in delta.record_changes}
                - covered
            )
            if uncovered:
                raise ObservationCohortUnavailableError(
                    "committed graph mutation is not closed by the accepted operations' "
                    "record intents: " + ", ".join(f"{kind} {record_id}" for kind, record_id in uncovered)
                )
        return tuple(emitted)

    def _boundary_stream_records(
        self, *, authority: DetachedSemanticObservationAuthority,
        membership: ResolvedObservationMembership,
    ) -> tuple[GraphObservationStreamRecord, ...]:
        """Emit every referenced-but-unchanged entity revision as a boundary record.

        A boundary entity is referenced through a selected delta's retained
        reference edges but is not itself changed by any selected delta.  Its
        observed payload derives only from the retained native record, its own
        retained type evidence, and its own retained commit events; a missing
        record, ambiguous authority, or unretained commit events deny instead
        of inventing a payload or a time.
        """
        referenced: set[str] = set()
        changed_entities: set[str] = set()
        for delta in membership.graph_deltas:
            for change in delta.record_changes:
                if change.record_kind == "entity_revision":
                    changed_entities.add(change.record_id)
                referenced.update(
                    edge.target.target_id
                    for edge in change.reference_edges_added
                    if edge.target.kind == "entity_revision"
                )
        boundary_ids = sorted(referenced - changed_entities)
        if not boundary_ids:
            return ()
        retained: dict[str, EntityRevision] = {}
        retained_type_evidence = tuple(
            record.payload for record in authority.graph.records
            if isinstance(record.payload, TypeEvidence)
        )
        for record in authority.graph.records:
            payload = record.payload
            if not isinstance(payload, EntityRevision):
                continue
            prior = retained.get(payload.entity_revision_id)
            if prior is not None and prior.logical_entity_id != payload.logical_entity_id:
                raise ObservationCohortUnavailableError("retained entity authority is ambiguous")
            retained[payload.entity_revision_id] = payload
        emitted: list[GraphObservationStreamRecord] = []
        for entity_revision_id in boundary_ids:
            payload = retained.get(entity_revision_id)
            if payload is None:
                raise ObservationCohortUnavailableError(
                    "referenced boundary entity revision is not retained by the detached authority"
                )
            owning = tuple(
                event for batch in authority.event_batches for event in batch.events
                if event.payload.record_kind == "entity_revision"
                and event.payload.record_id == entity_revision_id
                and event.payload.record_digest == payload.record_digest
            )
            if len(owning) != 1:
                raise ObservationCohortUnavailableError(
                    "boundary entity revision has no unique retained owning commit event"
                )
            interval = _event_derived_system_intervals(
                authority=authority,
                versions=((
                    "entity_revision", entity_revision_id, payload.record_digest,
                ),),
            )[("entity_revision", entity_revision_id)]
            emitted.append(project_boundary_entity_revision(
                payload,
                retained_type_evidence=retained_type_evidence,
                system_interval=interval,
                history=self._history, publication=self._publication, limits=self._limits,
            ))
        return tuple(emitted)

    def _project_operation(
        self, *, item: BootstrapGraphOperationStoreMaterializationInputV3,
        request: BootstrapGraphGroupCommitRequestV3, delta: GraphRevisionDelta,
        authority: DetachedSemanticObservationAuthority,
        commit_values: PlanningCommitValues,
        system_intervals: Mapping[tuple[str, str], TimeInterval],
        covered: set[tuple[str, str]],
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
            covered.add(identity)
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
            # Converse closure: every accepted-effect evidence pair must itself
            # be retained as committed records of this selected delta; a pair
            # whose citation or provenance is outside the committed inventory
            # denies instead of observing uncommitted evidence.
            for record in (citation, provenance):
                change = changes.get((record.record_kind, graph_record_id(record)))
                if change is None or change.after_digest != record.record_digest:
                    raise ObservationCohortUnavailableError(
                        "accepted effect evidence pair is not part of the committed "
                        "record inventory"
                    )
            evidence_pairs.append((citation, provenance))
        lookup = _native_entity_lookup(
            operation_records=tuple(materialized), authority=authority,
        )
        # Every projected native record is a changed record of a selected delta
        # and carries boundary=False; referenced-but-unchanged entities are
        # emitted separately by _boundary_stream_records with boundary=True.
        try:
            return project_native_graph_observation_stream(
                compilation=compilation,
                accepted_effect=effect,
                retained_native_records=tuple(materialized),
                evidence_pairs=tuple(evidence_pairs),
                commit_values=commit_values,
                authorizing_transaction_group_id=request.transaction_group_id,
                native_entity_lookup=lookup,
                system_intervals=system_intervals,
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
        changed_stream: tuple[GraphObservationStreamRecord, ...],
        boundary_stream: tuple[GraphObservationStreamRecord, ...],
        projections: ObservedProjectionPublicationSelection,
    ) -> GraphObservationCohortPreimage:
        reference = authority.references
        certificate = reference.audit_certificate
        if certificate is None:
            raise ObservationCohortUnavailableError("reference audit certificate is unavailable")
        changed_keys = {
            (item.record_kind, item.primary_key): GraphObservationRecordKey(
                record_kind=item.record_kind, primary_key=item.primary_key,
            )
            for item in changed_stream
        }
        keys = tuple(changed_keys[key] for key in sorted(changed_keys))
        boundary_keys_map = {
            (item.record_kind, item.primary_key): GraphObservationRecordKey(
                record_kind=item.record_kind, primary_key=item.primary_key,
            )
            for item in boundary_stream
        }
        boundary_keys = tuple(boundary_keys_map[key] for key in sorted(boundary_keys_map))
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
            temporal_projection_generation_digest=projections.temporal_generation_digest,
            temporal_projection_pointer_digest=projections.temporal_pointer_digest,
            trust_projection_generation_digest=projections.trust_generation_digest,
            trust_projection_pointer_digest=projections.trust_pointer_digest,
            observation_schema_fingerprint=_observation_schema_fingerprint(membership),
            changed_record_keys=keys, boundary_record_keys=boundary_keys,
        )


@dataclass(frozen=True)
class ObservedProjectionPublicationSelection:
    """The separately selected projection publications of one observation.

    Each generation/pointer pair is either both present or both null.  A null
    selection means the detached image retains no verified projection history
    before the first publication of either kind; it cannot stand in for an
    unread, invalid, or unavailable history at a requested historical
    coordinate, which denies instead.
    """

    temporal_generation_digest: str | None
    temporal_pointer_digest: str | None
    trust_generation_digest: str | None
    trust_pointer_digest: str | None
    records: tuple[GraphObservationStreamRecord, ...]


def project_observed_claim_projections(
    *,
    projection_history: ProjectionHistoryRepository,
    view: GraphObservationView,
    valid_at: datetime | None,
    system_as_of: datetime,
    graph_revision: str,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> ObservedProjectionPublicationSelection:
    """Emit the observed temporal/trust claim projections of one cohort.

    The publications come from the projection history retained in the same
    detached memory-plane image, never from graph deltas or a live read.  A
    current view selects each kind through its active pointer and requires the
    active generation to bind the requested graph revision; a historical view
    requires a valid time and selects each kind through its pointer at the
    requested system time.  Each observed record copies its complete native
    projection payload, generation digest, publication pointer, and same-kind
    successor pointer, carries the cohort-derived boundary flag, and takes its
    ``observation_id`` from the registered identity root of the selected
    publication.  Every ambiguous, absent, or substituted value denies.
    """

    temporal, trust = _select_projection_publications(
        projection_history, view=view, valid_at=valid_at, system_as_of=system_as_of,
        graph_revision=graph_revision,
    )
    if temporal is None or trust is None:
        return ObservedProjectionPublicationSelection(None, None, None, None, ())
    if not projection_observation_identity_root_selected(history, publication):
        raise ObservationCohortUnavailableError(
            "projection observation identity root is not selected"
        )
    records = (
        *_temporal_projection_records(
            temporal, projection_history=projection_history, history=history,
            publication=publication, limits=limits,
        ),
        *_trust_projection_records(
            trust, projection_history=projection_history, history=history,
            publication=publication, limits=limits,
        ),
    )
    return ObservedProjectionPublicationSelection(
        temporal_generation_digest=temporal.pointer.generation_digest,
        temporal_pointer_digest=temporal.pointer.pointer_digest,
        trust_generation_digest=trust.pointer.generation_digest,
        trust_pointer_digest=trust.pointer.pointer_digest,
        records=tuple(sorted(
            records, key=lambda item: (item.record_kind, item.primary_key)
        )),
    )


def _select_projection_publications(
    projection_history: ProjectionHistoryRepository,
    *,
    view: GraphObservationView,
    valid_at: datetime | None,
    system_as_of: datetime,
    graph_revision: str,
) -> tuple[TemporalProjectionView | None, TrustProjectionView | None]:
    """Apply the requested view/time to each kind's retained publication chain.

    A current view must not select a valid time; a historical view requires
    one, while the publication itself is selected at the requested system
    time.  The two kinds select independently through their own canonical
    rules; one kind's advance never substitutes or rewrites the other's
    coordinate.  A repository that retains no projection history at all is
    observable with null pairs before its first publication; anything absent
    or unreadable at a requested historical coordinate denies.
    """

    if view == "current" and valid_at is not None:
        raise ObservationCohortUnavailableError(
            "current projection view cannot select a valid time"
        )
    if view == "historical" and valid_at is None:
        raise ObservationCohortUnavailableError(
            "historical projection view requires a valid time"
        )
    try:
        bindings = projection_history.replay_bindings()
        if view == "current":
            if not bindings:
                return None, None
            temporal = projection_history.active_temporal_authority()
            trust = projection_history.active_trust_authority()
        elif view == "historical":
            if not bindings:
                raise ObservationCohortUnavailableError(
                    "selected projection publication is not retained in the detached image"
                )
            temporal = projection_history.historical_temporal(system_as_of=system_as_of)
            trust = projection_history.historical_trust(system_as_of=system_as_of)
        else:
            raise ObservationCohortUnavailableError(
                "requested projection view has no exact publication selection recipe"
            )
    except ProjectionHistoryError as exc:
        raise ObservationCohortUnavailableError(
            "selected projection publication is not retained in the detached image"
        ) from exc
    if view == "current":
        for kind, selected in (("temporal", temporal), ("trust", trust)):
            if selected.generation.base_graph_revision != graph_revision:
                raise ObservationCohortUnavailableError(
                    f"active {kind} projection generation does not bind the "
                    "requested graph revision"
                )
    return temporal, trust


def _temporal_projection_records(
    selected: TemporalProjectionView,
    *,
    projection_history: ProjectionHistoryRepository,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> tuple[GraphObservationStreamRecord, ...]:
    """Emit one observed temporal record per native projection of a publication."""
    successor = projection_history.publication_successor(
        "temporal", selected.pointer.pointer_digest
    )
    if not (successor is None or isinstance(successor, ActiveTemporalProjectionPointer)):
        raise ObservationCohortUnavailableError(
            "temporal projection successor pointer is substituted"
        )
    emitted: list[GraphObservationStreamRecord] = []
    for projection in selected.projections:
        payload = _emit_observed_projection(
            ObservedTemporalClaimProjection(
                observation_id=_derived_projection_identity(
                    "temporal", projection, selected.pointer,
                    history=history, publication=publication, limits=limits,
                ),
                projection=projection,
                generation_digest=selected.pointer.generation_digest,
                publication_pointer=selected.pointer,
                successor_publication_pointer=successor, boundary=True,
                record_digest="0" * 64,
            ),
            history=history, publication=publication, limits=limits,
        )
        emitted.append(TemporalClaimProjectionStreamRecord(
            record_kind="temporal_claim_projection", primary_key=payload.observation_id,
            record_digest=payload.record_digest, payload=payload,
        ))
    return tuple(emitted)


def _trust_projection_records(
    selected: TrustProjectionView,
    *,
    projection_history: ProjectionHistoryRepository,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> tuple[GraphObservationStreamRecord, ...]:
    """Emit one observed trust record per native projection of a publication."""
    successor = projection_history.publication_successor(
        "trust", selected.pointer.pointer_digest
    )
    if not (successor is None or isinstance(successor, ActiveTrustProjectionPointer)):
        raise ObservationCohortUnavailableError(
            "trust projection successor pointer is substituted"
        )
    emitted: list[GraphObservationStreamRecord] = []
    for projection in selected.projections:
        payload = _emit_observed_projection(
            ObservedTrustClaimProjection(
                observation_id=_derived_projection_identity(
                    "trust", projection, selected.pointer,
                    history=history, publication=publication, limits=limits,
                ),
                projection=projection,
                generation_digest=selected.pointer.generation_digest,
                publication_pointer=selected.pointer,
                successor_publication_pointer=successor, boundary=True,
                record_digest="0" * 64,
            ),
            history=history, publication=publication, limits=limits,
        )
        emitted.append(TrustClaimProjectionStreamRecord(
            record_kind="trust_claim_projection", primary_key=payload.observation_id,
            record_digest=payload.record_digest, payload=payload,
        ))
    return tuple(emitted)


def _derived_projection_identity(
    kind: Literal["temporal", "trust"],
    projection: TemporalProjectionRecord | TrustProjectionRecord,
    pointer: ActiveTemporalProjectionPointer | ActiveTrustProjectionPointer,
    *,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> str:
    """Derive one projection's registered outward identity, or deny."""
    try:
        return derive_projection_observation_identity(
            kind, projection.repository_id, pointer.generation_digest,
            projection.projection_digest, history=history, publication=publication,
            limits=limits,
        )
    except (ObservationActivationRuntimeError, TypedValueModelCodecCapacityError) as exc:
        raise ObservationCohortUnavailableError(
            f"observed {kind} projection identity cannot be derived"
        ) from exc


_ObservedProjectionT = TypeVar(
    "_ObservedProjectionT", ObservedTemporalClaimProjection, ObservedTrustClaimProjection,
)


def _emit_observed_projection(
    payload: _ObservedProjectionT,
    *,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> _ObservedProjectionT:
    """Emit one observed projection payload through the registered path.

    The registered emission supplies the real record digest and re-derives the
    identity; a record that is not identical to its own emission denies.
    """

    try:
        emitted = emit_registered_observation_artifact(
            payload, schema_id=type(payload).__name__, history=history,
            publication=publication, limits=limits,
        ).value
    except (ObservationActivationRuntimeError, TypedValueModelCodecCapacityError) as exc:
        raise ObservationCohortUnavailableError(
            "observed projection record cannot be emitted"
        ) from exc
    if type(emitted) is not type(payload) or emitted != payload.model_copy(
        update={"record_digest": emitted.record_digest}
    ):
        raise ObservationCohortUnavailableError(
            "observed projection record is substituted"
        )
    return emitted


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


def _event_derived_system_intervals(
    *, authority: DetachedSemanticObservationAuthority,
    versions: tuple[tuple[str, str, str], ...],
) -> dict[tuple[str, str], TimeInterval]:
    """Derive one commit-event-owned system interval per exact record version.

    The owning event is the retained event whose payload carries this exact
    record identity and digest.  The interval end is the successor event that
    advances this version, when one exists and is strictly later; a same-time
    successor keeps exact lineage with an unbounded end instead of inventing a
    positive interval.  Ambiguous ownership, ambiguous succession, or a
    successor that is not ordered after its owner denies.  No snapshot or
    request time is ever stamped on a record version.
    """
    intervals: dict[tuple[str, str], TimeInterval] = {}
    for record_kind, record_id, record_digest in versions:
        key = (record_kind, record_id)
        if key in intervals:
            continue
        owning: list[SemanticMemoryEvent] = []
        successors: list[SemanticMemoryEvent] = []
        for batch in authority.event_batches:
            for event in batch.events:
                payload = event.payload
                if payload.record_kind != record_kind or payload.record_id != record_id:
                    continue
                if payload.record_digest == record_digest:
                    owning.append(event)
                elif payload.prior_record_digest == record_digest:
                    successors.append(event)
        if len(owning) != 1:
            raise ObservationCohortUnavailableError(
                "record version has no unique owning commit event"
            )
        owner = owning[0]
        end: datetime | None = None
        if successors:
            if len(successors) > 1:
                raise ObservationCohortUnavailableError(
                    "record version has ambiguous successor commit events"
                )
            successor = successors[0]
            if successor.timestamp > owner.timestamp:
                end = successor.timestamp
            elif successor.timestamp < owner.timestamp:
                raise ObservationCohortUnavailableError(
                    "successor commit event is not ordered after its owning event"
                )
            # A same-time successor is ordered by sequence and retains exact
            # lineage with an unbounded end; no positive interval is invented.
        intervals[key] = TimeInterval(start=owner.timestamp, end=end)
    return intervals


def _native_entity_lookup(
    *, operation_records: tuple[object, ...], authority: DetachedSemanticObservationAuthority,
) -> dict[str, str]:
    """Resolve referenced entities' logical identities from retained authority.

    The lookup maps each entity revision id to its retained logical entity id;
    the projection owner constructs per-use-site observed references from
    these resolved identities.
    """
    lookup: dict[str, str] = {}

    def add(record: EntityRevision) -> None:
        prior = lookup.get(record.entity_revision_id)
        if prior is not None and prior != record.logical_entity_id:
            raise ObservationCohortUnavailableError("retained entity authority is ambiguous")
        lookup[record.entity_revision_id] = record.logical_entity_id

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


__all__ = [
    "AtomicStoreGraphObservationCohortProvider", "ObservedProjectionPublicationSelection",
    "project_observed_claim_projections",
]
