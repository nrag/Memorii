"""Registered projection of one verified retained native graph operation.

This owner converts exactly one already-verified accepted native operation
(the joined operation compilation, accepted effect, and complete retained
native record inventory) into observed graph-observation stream records.
It is a read-only view of retained authority: every field is copied or joined
from retained native records, the planning construction authority, or the
caller's verified evidence pairs.  No field is inferred from the caller,
current host policy, text, or model output, and no new stored graph
representation is created.

Every accepted arm uses its own exact recipe: fact and correction arms
project their exactly-one claim as before, correction arms additionally
project each retained temporal transition, retraction arms project their
transition records, action arms project each retained action revision, and
identity arms project their lineage record with its reference dispositions.
Action, identity and transition fields use their exact retained operation
authorities; a missing action transition, identity construction or retained
claim-slot authority is a typed refusal, never a guessed transition or a
rewritten identity.

Every ambiguous or unprovable join fails closed with
:class:`NativeGraphObservationProjectionError` carrying a distinctive
message; a partial or guessed observed record is never emitted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, TypeAlias, TypeVar

from pydantic import BaseModel

from memorii.core.memory_evolution.graph_observation_records import (
    ObservedActionRevision,
    ObservedActionRoleBinding,
    ObservedAliasRevision,
    ObservedAssertionEntityReference,
    ObservedAuthenticatedReferenceEffectiveTime,
    ObservedCertifiedTextEffectiveTime,
    ObservedCitationRecord,
    ObservedClaimAssertion,
    ObservedEntityReference,
    ObservedEntityRevision,
    ObservedIdentityTransition,
    ObservedProvenanceRecord,
    ObservedReferenceDisposition,
    ObservedRelation,
    ObservedSystemRecordedEffectiveTime,
    ObservedTemporalTransition,
    ObservedTypeEvidence,
)
from memorii.core.memory_evolution.graph_observation_streams import (
    ActionRevisionStreamRecord,
    AliasRevisionStreamRecord,
    CitationStreamRecord,
    ClaimAssertionStreamRecord,
    EntityRevisionStreamRecord,
    IdentityTransitionStreamRecord,
    ProvenanceStreamRecord,
    ReferenceDispositionStreamRecord,
    RelationStreamRecord,
    TemporalTransitionStreamRecord,
    TypeEvidenceStreamRecord,
)
from memorii.core.memory_evolution.graph_planning import (
    PlanningCommitValues,
    materialize_canonical_planning_payload,
)
from memorii.core.memory_evolution.graph_records import (
    AliasRevision,
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    ProvenanceRecord,
    ReferenceDispositionRecord,
    RelationRevision,
    TypeEvidence,
    graph_record_id,
    graph_record_union_member,
)
from memorii.core.memory_evolution.observation_activation_runtime import (
    emit_registered_observation_artifact,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_evolution.typed_value_artifact_reader import (
    ProtectedTypedValueArtifactReaderLimits,
)
from memorii.core.memory_evolution.typed_value_publication import (
    VerifiedTypedValuePublication,
)
from memorii.core.memory_evolution.typed_value_registry_history import (
    ProtectedTypedValueRegistryHistory,
)
from memorii.core.semantic_ingestion.contracts import (
    ActionRevision,
    AuthenticatedReferenceEffectiveTime,
    AuthenticatedSourceIntervalEvidence,
    BootstrapNativeAcceptedOperationEffectV3,
    BootstrapNativeActionStateEffectV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeEvidenceConstructionV3,
    BootstrapNativeEvidenceProjectionV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeIdentityEffectV3,
    BootstrapNativeOperationCompilationV3,
    BootstrapNativePlanningConstructionAuthorityV3,
    BootstrapNativePlanningRecordV3,
    BootstrapNativeRetractionEffectV3,
    BootstrapNativeTargetBindingV3,
    BootstrapNativeTemporalConstructionV3,
    BootstrapProposalActionRoleParticipantV3,
    BootstrapProposalFactV3,
    CertifiedTextEffectiveTime,
    ClaimAssertion,
    IdentityLineageRecord,
    SourceSpanReference,
    SystemRecordedEffectiveTime,
    TemporalTransitionRecord,
    TypedLiteral,
    contract_digest,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_records import CanonicalGraphRecord

ObservedEffectiveTimeValue: TypeAlias = (
    ObservedCertifiedTextEffectiveTime
    | ObservedAuthenticatedReferenceEffectiveTime
    | ObservedSystemRecordedEffectiveTime
)


class NativeGraphObservationProjectionError(ValueError):
    """The retained native authority cannot produce one exact observation."""


NativeGraphObservationStreamRecord: TypeAlias = (
    EntityRevisionStreamRecord
    | AliasRevisionStreamRecord
    | TypeEvidenceStreamRecord
    | ClaimAssertionStreamRecord
    | RelationStreamRecord
    | ActionRevisionStreamRecord
    | CitationStreamRecord
    | ProvenanceStreamRecord
    | TemporalTransitionStreamRecord
    | IdentityTransitionStreamRecord
    | ReferenceDispositionStreamRecord
)

_Observed = TypeVar(
    "_Observed",
    ObservedEntityRevision,
    ObservedAliasRevision,
    ObservedTypeEvidence,
    ObservedClaimAssertion,
    ObservedRelation,
    ObservedActionRevision,
    ObservedCitationRecord,
    ObservedProvenanceRecord,
    ObservedTemporalTransition,
    ObservedIdentityTransition,
    ObservedReferenceDisposition,
)

# Retained record kinds this projection can convert into observed records.
# ``claim_projection`` is a join helper for relation pairing and is not
# emitted; every other kind maps to exactly one observed stream family for
# the arm that owns it -- a kind retained by an arm with no projection recipe
# for it denies through the per-arm consumption closure below.
_SUPPORTED_RECORD_KINDS = frozenset({
    "entity_revision", "alias_revision", "type_evidence", "claim_assertion",
    "claim_projection", "relation_revision", "action_revision", "citation",
    "provenance", "temporal_transition", "identity_lineage",
    "reference_disposition",
})


def project_native_graph_observation_stream(
    *,
    compilation: BootstrapNativeOperationCompilationV3,
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    retained_native_records: Sequence[CanonicalGraphRecord],
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
    native_entity_lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> tuple[NativeGraphObservationStreamRecord, ...]:
    """Convert one verified retained native operation into observed records.

    The caller supplies one already-verified operation/effect join and the
    complete retained native record inventory.  Every planning record is
    re-materialized under the passed commit coordinates and must match the
    retained inventory exactly; any metadata or inventory substitution
    denies.  Each observed payload is emitted through the registered
    observation runtime to obtain its real record digest.  ``system_intervals``
    supplies one commit-event-owned interval per exact changed record version,
    keyed by ``(record_kind, record_id)``; this owner never samples a clock and
    never stamps a request or snapshot time on an observed payload.
    """
    authority = compilation.operation_input.planning_construction_authority
    if authority is None or (
        compilation.terminal_status != "accepted"
        or authority.operation_id != compilation.operation_id
        or authority.operation_execution_id != compilation.operation_execution_id
    ):
        raise NativeGraphObservationProjectionError("native operation authority is incomplete")
    if commit_values.transaction_group_id != authorizing_transaction_group_id:
        raise NativeGraphObservationProjectionError("commit authority group is substituted")

    evidence_projections, planning_records, effect_digests, fact = _effect_authority(
        accepted_effect, compilation=compilation,
    )
    records: tuple[CanonicalGraphRecord, ...] = _materialized_records(
        planning_records,
        retained_native_records=retained_native_records,
        commit_values=commit_values,
        authorizing_transaction_group_id=authorizing_transaction_group_id,
        operation_id=compilation.operation_id,
        operation_execution_id=compilation.operation_execution_id,
    )
    _require_supported_record_kinds(records)
    inventory_entities = {
        value.entity_revision_id for value in records if isinstance(value, EntityRevision)
    }
    _require_retained_inventory_closed(
        records,
        inventory_entities=inventory_entities,
        retained_native_records=retained_native_records,
    )

    claims = [value for value in records if isinstance(value, ClaimAssertion)]
    if isinstance(accepted_effect, (BootstrapNativeFactEffectV3, BootstrapNativeCorrectionEffectV3)):
        if len(claims) != 1:
            raise NativeGraphObservationProjectionError(
                "accepted operation arm does not retain exactly one claim assertion"
            )
    elif isinstance(
        accepted_effect, (BootstrapNativeRetractionEffectV3, BootstrapNativeIdentityEffectV3)
    ) and claims:
        raise NativeGraphObservationProjectionError(
            "accepted operation arm retains a claim assertion it does not own"
        )
    claim = claims[0] if claims else None
    # The canonical-type cohort is closed to evidence that binds one entity
    # revision of this operation's inventory; evidence bound to foreign
    # entities or revisions neither joins a type nor survives the inventory
    # closure above.  ``_canonical_type`` still matches the exact revision id
    # per asserted entity, so foreign-bound evidence never supplies a type.
    type_evidence_cohort = tuple(
        value for value in retained_native_records
        if isinstance(value, TypeEvidence)
        and isinstance(value.entity_reference, CanonicalEntityRevisionRef)
        and value.entity_reference.entity_revision_id in inventory_entities
    )
    retained_spans = tuple(
        construction.source_span
        for construction in authority.evidence_constructions
    )
    policy_fingerprints = _policy_context(compilation)

    emitted: list[NativeGraphObservationStreamRecord] = []
    for value in records:
        if isinstance(value, EntityRevision):
            emitted.append(_entity_revision(
                value, type_evidence_cohort=type_evidence_cohort, lookup=native_entity_lookup,
                authority_source_id=authority.source_id, system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, AliasRevision):
            emitted.append(_alias_revision(
                value, lookup=native_entity_lookup, authority_source_id=authority.source_id,
                system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, TypeEvidence):
            emitted.append(_type_evidence(
                value, retained_spans=retained_spans, lookup=native_entity_lookup,
                system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
    for value in claims:
        emitted.append(_claim(
            value, fact, evidence_pairs=evidence_pairs,
            policy_fingerprints=policy_fingerprints,
            lookup=native_entity_lookup, system_intervals=system_intervals,
            history=history, publication=publication, limits=limits,
        ))
    for value in records:
        if isinstance(value, RelationRevision):
            if claim is None:
                raise NativeGraphObservationProjectionError(
                    "relation has no exactly paired supporting claim"
                )
            emitted.append(_relation(
                value, claim, records=records, evidence_pairs=evidence_pairs,
                lookup=native_entity_lookup, system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, ActionRevision):
            emitted.append(_action_revision(
                value, accepted_effect=accepted_effect, claims=claims,
                records=records, authority=authority, compilation=compilation,
                evidence_pairs=evidence_pairs, lookup=native_entity_lookup,
                system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, TemporalTransitionRecord):
            emitted.append(_temporal_transition(
                value, accepted_effect=accepted_effect, claims=claims,
                authority=authority, evidence_pairs=evidence_pairs,
                system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, IdentityLineageRecord):
            emitted.append(_identity_transition(
                value, accepted_effect=accepted_effect, authority=authority,
                retained_spans=retained_spans, lookup=native_entity_lookup,
                system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, ReferenceDispositionRecord):
            emitted.append(_reference_disposition(
                value, accepted_effect=accepted_effect, records=records,
                lookup=native_entity_lookup, system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, CitationRecord):
            emitted.append(_citation(
                value, records=records, evidence_projections=evidence_projections,
                authority=authority, history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, ProvenanceRecord):
            emitted.append(_provenance(
                value, records=records, evidence_projections=evidence_projections,
                authority=authority, compilation=compilation, effect_digests=effect_digests,
                policy_fingerprints=policy_fingerprints, system_intervals=system_intervals,
                history=history, publication=publication, limits=limits,
            ))
    _require_records_consumed(records, emitted)
    keys = [(item.record_kind, item.primary_key) for item in emitted]
    if len(keys) != len(set(keys)):
        raise NativeGraphObservationProjectionError(
            "retained native inventory has duplicate identities"
        )
    return tuple(sorted(emitted, key=lambda item: (item.record_kind, item.primary_key)))


def _effect_authority(
    effect: BootstrapNativeAcceptedOperationEffectV3,
    *,
    compilation: BootstrapNativeOperationCompilationV3,
) -> tuple[
    tuple[BootstrapNativeEvidenceProjectionV3, ...],
    tuple[BootstrapNativePlanningRecordV3, ...],
    tuple[str, ...],
    BootstrapProposalFactV3 | None,
]:
    """Select retained records and the closed digest path for every native arm.

    The typed dispatch mirrors the approved retained provenance design: each
    accepted arm names its own evidence projections, planning records, and
    effect digest path.  Every arm must still bind the compilation's exact
    operation member.
    """
    if isinstance(effect, BootstrapNativeFactEffectV3):
        if effect.fact != compilation.operation_member:
            raise NativeGraphObservationProjectionError(
                "accepted effect does not bind the compilation operation member"
            )
        return effect.evidence_projections, effect.planning_records, (effect.effect_digest,), effect.fact
    if isinstance(effect, BootstrapNativeCorrectionEffectV3):
        if effect.correction != compilation.operation_member:
            raise NativeGraphObservationProjectionError(
                "accepted effect does not bind the compilation operation member"
            )
        replacement = effect.replacement_effect
        expected_transitions = tuple(
            item for item in replacement.planning_records
            if item.record_kind == "temporal_transition"
        )
        if effect.transition_records != expected_transitions:
            raise NativeGraphObservationProjectionError(
                "correction transition view differs from its canonical record owner"
            )
        return (
            replacement.evidence_projections,
            replacement.planning_records,
            (effect.effect_digest, replacement.effect_digest),
            replacement.fact,
        )
    if isinstance(effect, BootstrapNativeRetractionEffectV3):
        if effect.retraction != compilation.operation_member:
            raise NativeGraphObservationProjectionError(
                "accepted effect does not bind the compilation operation member"
            )
        # The retraction universe is its transition records plus the citation
        # and provenance records retained on the effect's own evidence
        # projections; fact/correction/action arms carry those inside their
        # planning records already.
        return (
            effect.evidence_projections,
            (
                *effect.transition_records,
                *(
                    record
                    for projection in effect.evidence_projections
                    for record in (projection.citation_record, projection.provenance_record)
                ),
            ),
            (effect.effect_digest,),
            None,
        )
    if isinstance(effect, BootstrapNativeActionStateEffectV3):
        if effect.action_state != compilation.operation_member:
            raise NativeGraphObservationProjectionError(
                "accepted effect does not bind the compilation operation member"
            )
        return effect.evidence_projections, effect.planning_records, (effect.effect_digest,), None
    if isinstance(effect, BootstrapNativeIdentityEffectV3):
        if effect.identity_operation != compilation.operation_member:
            raise NativeGraphObservationProjectionError(
                "accepted effect does not bind the compilation operation member"
            )
        materialization = effect.materialization
        return (
            effect.evidence_projections,
            (
                *materialization.revision_and_alias_records,
                materialization.lineage_record,
                *materialization.reference_disposition_records,
                *(
                    record
                    for projection in effect.evidence_projections
                    for record in (projection.citation_record, projection.provenance_record)
                ),
            ),
            (effect.effect_digest,),
            None,
        )
    raise NativeGraphObservationProjectionError(
        "accepted operation arm has no exact observed projection recipe"
    )


def _require_supported_record_kinds(records: Sequence[CanonicalGraphRecord]) -> None:
    """Deny any retained record this projection cannot convert exactly."""
    unsupported = sorted({
        value.record_kind for value in records
        if value.record_kind not in _SUPPORTED_RECORD_KINDS
    })
    if unsupported:
        raise NativeGraphObservationProjectionError(
            "retained native record kind has no exact observed projection recipe: "
            + ", ".join(unsupported)
        )


def _require_retained_inventory_closed(
    records: Sequence[CanonicalGraphRecord],
    *,
    inventory_entities: set[str],
    retained_native_records: Sequence[CanonicalGraphRecord],
) -> None:
    """Require the planning records to close the retained native inventory.

    The converse of ``_materialized_records``: every retained record is
    consumed by this operation's materialized planning set or is one of the
    recognized non-emitting join helpers.  ``claim_projection`` is the
    documented join helper for relation pairing; retained type evidence joins
    into entity canonical types only while it binds one entity revision of
    this closed inventory.  Any other unmatched retained record -- including
    evidence bound to foreign entities or revisions -- has no consumed role
    and denies instead of riding along silently.
    """
    planned = {
        (value.record_kind, graph_record_id(value)) for value in records
    }
    for value in retained_native_records:
        key = (value.record_kind, graph_record_id(value))
        if key in planned:
            continue
        if isinstance(value, ClaimProjection) or (
            isinstance(value, TypeEvidence)
            and isinstance(value.entity_reference, CanonicalEntityRevisionRef)
            and value.entity_reference.entity_revision_id in inventory_entities
        ):
            continue
        raise NativeGraphObservationProjectionError(
            "retained native inventory is not closed by the operation's planning records: "
            + f"{value.record_kind} {graph_record_id(value)}"
        )


def _require_records_consumed(
    records: Sequence[CanonicalGraphRecord],
    emitted: Sequence[NativeGraphObservationStreamRecord],
) -> None:
    """Require every retained record to feed exactly one observed payload.

    The per-arm dispatch above is exhaustive over the supported kinds only for
    the arm that owns each kind; a record kind retained by an arm with no
    projection recipe for it (for example a reference disposition retained by
    a fact arm) must deny instead of riding along silently.  ``claim_projection``
    is the documented non-emitting join helper.
    """
    consumed = {(item.record_kind, item.primary_key) for item in emitted}
    stream_kinds = {"relation_revision": "relation", "identity_lineage": "identity_transition"}
    for value in records:
        if isinstance(value, ClaimProjection):
            continue
        stream_kind = stream_kinds.get(value.record_kind, value.record_kind)
        if (stream_kind, graph_record_id(value)) not in consumed:
            raise NativeGraphObservationProjectionError(
                "retained native record has no exact observed projection recipe "
                f"for this operation arm: {value.record_kind} {graph_record_id(value)}"
            )


def _materialized_records(
    planning_records: Sequence[BootstrapNativePlanningRecordV3],
    *,
    retained_native_records: Sequence[CanonicalGraphRecord],
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
    operation_id: str,
    operation_execution_id: str,
) -> tuple[CanonicalGraphRecord, ...]:
    """Re-materialize every planning record and require exact retained match."""
    retained: dict[tuple[str, str], CanonicalGraphRecord] = {
        (item.record_kind, graph_record_id(item)): item for item in retained_native_records
    }
    if len(retained) != len(retained_native_records):
        raise NativeGraphObservationProjectionError(
            "retained native inventory has duplicate identities"
        )
    materialized: list[CanonicalGraphRecord] = []
    for record in planning_records:
        value = materialize_canonical_planning_payload(
            record.planning_payload, commit_values=commit_values,
            authorizing_transaction_group_id=authorizing_transaction_group_id,
        )
        if not graph_record_union_member(value):
            raise NativeGraphObservationProjectionError(
                "materialized native record is not a canonical graph record"
            )
        key = (value.record_kind, graph_record_id(value))
        if (
            record.operation_execution_id != operation_execution_id
            or record.record_kind != value.record_kind
            or record.record_id != graph_record_id(value)
            or value.operation_id != operation_id
            or retained.get(key) != value
        ):
            raise NativeGraphObservationProjectionError(
                "native record differs from canonical materialization"
            )
        materialized.append(value)
    return tuple(materialized)


def _policy_context(
    compilation: BootstrapNativeOperationCompilationV3,
) -> tuple[str, ...]:
    """Deduplicated sorted policy fingerprints of the retained authority."""
    authority = compilation.operation_input.planning_construction_authority
    if authority is None:
        raise NativeGraphObservationProjectionError("native operation authority is incomplete")
    values = {
        authority.predicate_registry_fingerprint,
        authority.predicate_state_rule.policy_fingerprint,
        authority.action_policy_fingerprint,
        *(item.temporal_policy_fingerprint for item in authority.temporal_constructions),
    }
    if authority.identity_construction is not None:
        values.add(authority.identity_construction.identity_policy_fingerprint)
    if authority.arbitration_policy_bundle is not None:
        values.update((
            authority.arbitration_policy_bundle.trust_policy.fingerprint,
            authority.arbitration_policy_bundle.temporal_policy.fingerprint,
        ))
    return tuple(sorted(values))


def _emit(
    value: _Observed,
    schema_id: str,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> _Observed:
    """Emit one observed payload under its registered root for its real digest."""
    emitted = emit_registered_observation_artifact(
        value, schema_id=schema_id, history=history, publication=publication, limits=limits,
    ).value
    if not isinstance(emitted, type(value)):
        raise NativeGraphObservationProjectionError("registered observed payload is substituted")
    return emitted


def _lookup_reference(
    lookup: Mapping[str, str],
    entity_revision_id: str,
    *,
    logical_entity_id: str | None = None,
) -> str:
    """Resolve one entity revision's retained logical identity, or deny."""
    resolved = lookup.get(entity_revision_id)
    if resolved is None or (logical_entity_id is not None and resolved != logical_entity_id):
        raise NativeGraphObservationProjectionError("native entity lookup is incomplete")
    return resolved


# Per-use-site entity reference field paths, copying the native
# ``extract_reference_edges`` convention exactly: each observed entity
# reference carries the field path of the referencing record that produced it.
_ALIAS_ENTITY_REFERENCE_PATH = "entity_revision_id"
_TYPE_EVIDENCE_ENTITY_REFERENCE_PATH = "entity_reference.entity_revision_id"
_CLAIM_SUBJECT_REFERENCE_PATH = "/claim_identity/subject_assertion_ref/entity_revision_id"
_CLAIM_OBJECT_REFERENCE_PATH = "/claim_identity/object_assertion_ref/entity_revision_id"
_RELATION_SUBJECT_REFERENCE_PATH = "subject_entity_revision_id"
_RELATION_OBJECT_REFERENCE_PATH = "object_entity_revision_id"
# Action role bindings carry no native record reference edges; their observed
# entities derive from the action authority's participant bindings, so the
# per-use-site path names the participant site on that retained authority.
_ACTION_ROLE_PARTICIPANT_REFERENCE_PATH = "action_state.role_bindings[].participants[]"
_IDENTITY_PREDECESSOR_REFERENCE_PATH = "transition.predecessors[].entity_revision_id"
_IDENTITY_SUCCESSOR_REFERENCE_PATH = "transition.successors[].entity_revision_id"
_DISPOSITION_PREDECESSOR_REFERENCE_PATH = "predecessor_entity_revision_id"
_DISPOSITION_SUCCESSOR_REFERENCE_PATH = "successor_entity_revision_ids[]"


def _entity_reference(
    lookup: Mapping[str, str],
    entity_revision_id: str,
    *,
    reference_path: str,
    logical_entity_id: str | None = None,
) -> ObservedEntityReference:
    """Construct one per-use-site observed entity reference from the lookup."""
    return ObservedEntityReference(
        entity_revision_id=entity_revision_id,
        logical_entity_id=_lookup_reference(
            lookup, entity_revision_id, logical_entity_id=logical_entity_id,
        ),
        reference_path=reference_path,
    )


def _system_interval(
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    record_kind: str,
    record_id: str,
) -> TimeInterval:
    """One commit-event-owned interval for this exact record version, or deny."""
    interval = system_intervals.get((record_kind, record_id))
    if interval is None:
        raise NativeGraphObservationProjectionError(
            f"observed {record_kind} has no commit-event-derived system interval"
        )
    return interval


def _canonical_type(
    entity_revision: EntityRevision,
    cohort: Sequence[TypeEvidence],
) -> str | None:
    """Unique independently retained type asserted on this exact revision."""
    asserted: set[str] = set()
    for evidence in cohort:
        reference = evidence.entity_reference
        if not isinstance(reference, CanonicalEntityRevisionRef):
            continue
        if reference.entity_revision_id != entity_revision.entity_revision_id:
            continue
        if reference.logical_entity_id != entity_revision.logical_entity_id:
            raise NativeGraphObservationProjectionError(
                "entity type evidence binds a foreign logical entity"
            )
        asserted.add(evidence.asserted_type)
    if len(asserted) > 1:
        raise NativeGraphObservationProjectionError("competing entity type evidence")
    return next(iter(asserted)) if asserted else None


def _entity_revision(
    record: EntityRevision,
    *,
    type_evidence_cohort: Sequence[TypeEvidence],
    lookup: Mapping[str, str],
    authority_source_id: str,
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> EntityRevisionStreamRecord:
    _lookup_reference(
        lookup, record.entity_revision_id, logical_entity_id=record.logical_entity_id,
    )
    payload = _emit(ObservedEntityRevision(
        entity_revision_id=record.entity_revision_id, logical_entity_id=record.logical_entity_id,
        canonical_type=_canonical_type(record, type_evidence_cohort),
        lifecycle_state=record.lifecycle, valid_interval=None,
        system_interval=_system_interval(
            system_intervals, "entity_revision", record.entity_revision_id,
        ),
        source_ids=tuple(sorted({
            item.source_id for item in record.source_evidence
        } | {authority_source_id})),
        operation_ids=(record.operation_id,),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedEntityRevision", history, publication, limits)
    return EntityRevisionStreamRecord(
        record_kind="entity_revision", primary_key=payload.entity_revision_id,
        record_digest=payload.record_digest, payload=payload,
    )


def project_boundary_entity_revision(
    record: EntityRevision,
    *,
    retained_type_evidence: Sequence[TypeEvidence],
    system_interval: TimeInterval,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> EntityRevisionStreamRecord:
    """Emit one referenced-but-unchanged entity revision as a boundary record.

    The payload is derived only from the retained native record and its own
    retained evidence: ``canonical_type`` comes from eligible retained type
    evidence bound to this exact revision (``None`` when none exists),
    ``source_ids`` are the record's own lineage source references only, and
    ``operation_ids`` are that exact version's own native operation.  The
    caller must supply this record's own commit-event-derived interval.
    """
    payload = _emit(ObservedEntityRevision(
        entity_revision_id=record.entity_revision_id, logical_entity_id=record.logical_entity_id,
        canonical_type=_canonical_type(record, retained_type_evidence),
        lifecycle_state=record.lifecycle, valid_interval=None,
        system_interval=system_interval,
        source_ids=tuple(sorted({
            item.source_id for item in record.source_evidence
        })),
        operation_ids=(record.operation_id,),
        boundary=True,
        record_digest="0" * 64,
    ), "ObservedEntityRevision", history, publication, limits)
    return EntityRevisionStreamRecord(
        record_kind="entity_revision", primary_key=payload.entity_revision_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _alias_revision(
    record: AliasRevision,
    *,
    lookup: Mapping[str, str],
    authority_source_id: str,
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> AliasRevisionStreamRecord:
    reference = _entity_reference(
        lookup, record.entity_revision_id,
        reference_path=_ALIAS_ENTITY_REFERENCE_PATH,
        logical_entity_id=record.logical_entity_id,
    )
    payload = _emit(ObservedAliasRevision(
        alias_revision_id=record.alias_revision_id, entity=reference,
        alias_namespace=record.alias_namespace,
        normalized_alias_key=record.normalized_alias_key,
        binding_evidence_ids=tuple(item.evidence_digest for item in record.source_evidence),
        valid_interval=None, system_interval=_system_interval(
            system_intervals, "alias_revision", record.alias_revision_id,
        ),
        source_ids=tuple(sorted({
            item.source_id for item in record.source_evidence
        } | {authority_source_id})),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedAliasRevision", history, publication, limits)
    return AliasRevisionStreamRecord(
        record_kind="alias_revision", primary_key=payload.alias_revision_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _resolve_complete_source_span(
    candidate_spans: Sequence[SourceSpanReference],
    *,
    source_id: str,
    start: int,
    end: int,
) -> SourceSpanReference:
    """Copy the uniquely matched complete retained source span."""
    matches = [
        span for span in candidate_spans
        if span.source_id == source_id
        and span.segment_local_span.start == start
        and span.segment_local_span.end == end
    ]
    if not matches:
        raise NativeGraphObservationProjectionError("no complete retained source span")
    if len(matches) > 1:
        raise NativeGraphObservationProjectionError("ambiguous retained source span")
    return matches[0]


def _type_evidence(
    record: TypeEvidence,
    *,
    retained_spans: Sequence[SourceSpanReference],
    lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> TypeEvidenceStreamRecord:
    """Copy a retained type evidence with complete source-span evidence.

    A LineageEvidenceReference alone cannot manufacture a source span: every
    lineage reference must resolve to one uniquely matched complete retained
    SourceSpanReference carrying the artifact and mapping proof.
    """
    reference = record.entity_reference
    if not isinstance(reference, CanonicalEntityRevisionRef):
        raise NativeGraphObservationProjectionError(
            "type evidence does not bind one exact entity revision"
        )
    entity = _entity_reference(
        lookup, reference.entity_revision_id,
        reference_path=_TYPE_EVIDENCE_ENTITY_REFERENCE_PATH,
        logical_entity_id=reference.logical_entity_id,
    )
    payload = _emit(ObservedTypeEvidence(
        evidence_id=record.evidence_id, entity=entity, asserted_type=record.asserted_type,
        origin=record.origin,
        source_evidence=tuple(
            _resolve_complete_source_span(
                retained_spans, source_id=item.source_id, start=item.start, end=item.end,
            )
            for item in record.source_evidence
        ),
        proof_ancestry_ids=record.proof_ancestry_ids,
        proof_policy_fingerprint=record.proof_policy_fingerprint,
        valid_interval=record.valid_interval, system_interval=_system_interval(
            system_intervals, "type_evidence", record.evidence_id,
        ),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedTypeEvidence", history, publication, limits)
    return TypeEvidenceStreamRecord(
        record_kind="type_evidence", primary_key=payload.evidence_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _interval_evidence(claim: ClaimAssertion | ActionRevision):
    """The single retained authenticated interval evidence of selected candidates."""
    closure = claim.temporal_evidence.decision_closure
    selected = set(closure.selected_candidate_ids)
    evidences: dict[str, AuthenticatedSourceIntervalEvidence] = {}
    for candidate in closure.candidates:
        evidence = candidate.authenticated_source_interval_evidence
        if candidate.candidate_id in selected and evidence is not None:
            evidences.setdefault(evidence.evidence_digest, evidence)
    if len(evidences) > 1:
        raise NativeGraphObservationProjectionError(
            "ambiguous retained authenticated interval evidence"
        )
    return next(iter(evidences.values())) if evidences else None


def _claim(
    claim: ClaimAssertion,
    fact: BootstrapProposalFactV3 | None,
    *,
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
    policy_fingerprints: tuple[str, ...],
    lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> ClaimAssertionStreamRecord:
    identity = claim.claim_identity
    authority_evidence = claim.source_authority_evidence
    if identity is None or authority_evidence is None:
        raise NativeGraphObservationProjectionError(
            "claim assertion lacks its retained accepted identity"
        )
    if fact is None:
        raise NativeGraphObservationProjectionError(
            "claim polarity lacks its retained operation authority"
        )
    subject = identity.subject_assertion_ref
    value = identity.assertion_key_at_recording.value
    literal = None
    if value.object_kind == "literal":
        literal = TypedLiteral.create(
            literal_type=value.literal_type,
            canonical_value=value.canonical_literal_value,
            unit=None,
        )
    object_assertion_ref = None
    if identity.object_assertion_ref is not None:
        object_assertion_ref = ObservedAssertionEntityReference(
            entity=_entity_reference(
                lookup, identity.object_assertion_ref.entity_revision_id,
                reference_path=_CLAIM_OBJECT_REFERENCE_PATH,
            ),
            logical_entity_id_at_assertion=identity.object_assertion_ref.logical_entity_id_at_assertion,
        )
    citing = tuple(
        pair for pair in evidence_pairs
        if pair[0].cited_record_id == claim.claim_assertion_id
    )
    payload = _emit(ObservedClaimAssertion(
        claim_assertion_id=claim.claim_assertion_id,
        subject_assertion_ref=ObservedAssertionEntityReference(
            entity=_entity_reference(
                lookup, subject.entity_revision_id,
                reference_path=_CLAIM_SUBJECT_REFERENCE_PATH,
            ),
            logical_entity_id_at_assertion=subject.logical_entity_id_at_assertion,
        ),
        object_assertion_ref=object_assertion_ref,
        assertion_key_at_recording=identity.assertion_key_at_recording,
        predicate_id=identity.assertion_key_at_recording.slot.predicate_id,
        literal_value=literal, polarity=fact.polarity, commitment=fact.commitment,
        scope_identity=identity.assertion_key_at_recording.slot.scope_identity,
        valid_interval=claim.valid_interval,
        temporal_reference_evidence=claim.temporal_evidence.reference_evidence,
        authenticated_source_interval_evidence=_interval_evidence(claim),
        temporal_decision_binding=claim.temporal_decision_binding,
        system_interval=_system_interval(
            system_intervals, "claim_assertion", claim.claim_assertion_id,
        ),
        source_authority_class=authority_evidence.authority.authority_class,
        source_ids=(authority_evidence.source_id,),
        operation_ids=(claim.operation_id,),
        citation_ids=tuple(sorted({pair[0].citation_id for pair in citing})),
        provenance_ids=tuple(sorted({pair[1].provenance_id for pair in citing})),
        policy_fingerprints=policy_fingerprints,
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedClaimAssertion", history, publication, limits)
    return ClaimAssertionStreamRecord(
        record_kind="claim_assertion", primary_key=payload.claim_assertion_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _claim_predicate_id(claim: ClaimAssertion) -> str | None:
    identity = claim.claim_identity
    if identity is None:
        return None
    return identity.assertion_key_at_recording.slot.predicate_id


def _projection_binds_relation(
    projection: ClaimProjection, relation: RelationRevision, predicate_id: str,
) -> bool:
    return (
        predicate_id == relation.predicate_id
        and projection.subject_entity_revision_id == relation.subject_entity_revision_id
        and projection.subject_logical_entity_id == relation.subject_logical_entity_id
        and projection.object_entity_revision_id == relation.object_entity_revision_id
        and projection.object_logical_entity_id == relation.object_logical_entity_id
    )


def _claim_payload_binds_projection(
    claim: ClaimAssertion, projection: ClaimProjection,
) -> bool:
    """Canonical payload equality between the claim and its projection join."""
    identity = claim.claim_identity
    if identity is None:
        return False
    slot = identity.assertion_key_at_recording.slot
    value = identity.assertion_key_at_recording.value
    if slot.subject_logical_entity_id != projection.subject_logical_entity_id:
        return False
    if value.object_kind == "entity":
        if projection.object_entity_revision_id is None:
            return False
        if value.object_logical_entity_id != projection.object_logical_entity_id:
            return False
    elif projection.object_entity_revision_id is not None:
        return False
    return True


def _supporting_claims(
    relation: RelationRevision,
    claims: Sequence[ClaimAssertion],
    projections: Sequence[ClaimProjection],
) -> tuple[ClaimAssertion, ...]:
    supporting = []
    for claim in claims:
        predicate_id = _claim_predicate_id(claim)
        if predicate_id is None:
            continue
        if any(
            projection.claim_assertion_id == claim.claim_assertion_id
            and _projection_binds_relation(projection, relation, predicate_id)
            and _claim_payload_binds_projection(claim, projection)
            for projection in projections
        ):
            supporting.append(claim)
    supporting_ids = [claim.claim_assertion_id for claim in supporting]
    if len(set(supporting_ids)) != len(supporting_ids):
        raise NativeGraphObservationProjectionError("ambiguous relation claim pairing")
    return tuple(supporting)


def _intersect_valid_intervals(
    intervals: Sequence[TimeInterval | None],
) -> TimeInterval | None:
    if not intervals:
        raise NativeGraphObservationProjectionError(
            "relation has no exactly paired supporting claim"
        )
    bounded = [item for item in intervals if item is not None]
    if not bounded:
        return None
    start = max(item.start for item in bounded)
    ends = [item.end for item in bounded if item.end is not None]
    end = min(ends) if ends else None
    if end is not None and end <= start:
        raise NativeGraphObservationProjectionError(
            "supporting claim interval disagreement"
        )
    return TimeInterval(start=start, end=end)


def _relation(
    record: RelationRevision,
    claim: ClaimAssertion,
    *,
    records: Sequence[BaseModel],
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
    lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> RelationStreamRecord:
    projections = tuple(
        value for value in records if isinstance(value, ClaimProjection)
    )
    supporting = _supporting_claims(record, (claim,), projections)
    if not supporting:
        raise NativeGraphObservationProjectionError(
            "relation has no exactly paired supporting claim"
        )
    supporting_ids = tuple(item.claim_assertion_id for item in supporting)
    payload = _emit(ObservedRelation(
        relation_id=record.relation_revision_id, predicate_id=record.predicate_id,
        subject=_entity_reference(
            lookup, record.subject_entity_revision_id,
            reference_path=_RELATION_SUBJECT_REFERENCE_PATH,
            logical_entity_id=record.subject_logical_entity_id,
        ),
        object_kind="entity",
        object_entity=_entity_reference(
            lookup, record.object_entity_revision_id,
            reference_path=_RELATION_OBJECT_REFERENCE_PATH,
            logical_entity_id=record.object_logical_entity_id,
        ),
        literal_value=None,
        supporting_claim_assertion_ids=tuple(sorted(supporting_ids)),
        lifecycle_state="active",
        valid_interval=_intersect_valid_intervals(
            [item.valid_interval for item in supporting]
        ),
        system_interval=_system_interval(
            system_intervals, "relation_revision", record.relation_revision_id,
        ),
        source_ids=tuple(sorted({
            item.source_authority_evidence.source_id
            for item in supporting
            if item.source_authority_evidence is not None
        })),
        provenance_ids=tuple(sorted({
            provenance.provenance_id
            for citation, provenance in evidence_pairs
            if citation.cited_record_id in set(supporting_ids)
        })),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedRelation", history, publication, limits)
    return RelationStreamRecord(
        record_kind="relation", primary_key=payload.relation_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _unique_evidence_projection(
    evidence_projections: Sequence[BootstrapNativeEvidenceProjectionV3],
    *,
    citation_record_id: str | None = None,
    provenance_record_id: str | None = None,
) -> BootstrapNativeEvidenceProjectionV3:
    matches = tuple(
        projection for projection in evidence_projections
        if (citation_record_id is None or projection.citation_record.record_id == citation_record_id)
        and (provenance_record_id is None or projection.provenance_record.record_id == provenance_record_id)
    )
    if len(matches) != 1:
        raise NativeGraphObservationProjectionError(
            "nonunique retained evidence projection pairing"
        )
    return matches[0]


def _cited_target(records: Sequence[CanonicalGraphRecord], cited_record_id: str) -> CanonicalGraphRecord:
    targets = tuple(
        value for value in records if graph_record_id(value) == cited_record_id
    )
    if len(targets) != 1:
        raise NativeGraphObservationProjectionError(
            "nonunique or missing cited native target"
        )
    return targets[0]


def _citation(
    record: CitationRecord,
    *,
    records: Sequence[CanonicalGraphRecord],
    evidence_projections: Sequence[BootstrapNativeEvidenceProjectionV3],
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> CitationStreamRecord:
    projection = _unique_evidence_projection(
        evidence_projections, citation_record_id=record.citation_id,
    )
    construction = _retained_evidence_construction(
        authority, projection, citation_record_id=record.citation_id,
    )
    target = _cited_target(records, record.cited_record_id)
    payload = _emit(ObservedCitationRecord(
        citation_id=record.citation_id, cited_record_kind=target.record_kind,
        cited_record_id=record.cited_record_id,
        source_id=construction.source_span.source_id,
        source_span=construction.source_span,
        source_digest=authority.source_digest,
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedCitationRecord", history, publication, limits)
    return CitationStreamRecord(
        record_kind="citation", primary_key=payload.citation_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _retained_evidence_construction(
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    projection: BootstrapNativeEvidenceProjectionV3,
    *,
    citation_record_id: str,
) -> BootstrapNativeEvidenceConstructionV3:
    constructions = tuple(
        item for item in authority.evidence_constructions
        if item.evidence_item_digest == projection.evidence_item_digest
    )
    if len(constructions) != 1:
        raise NativeGraphObservationProjectionError(
            "nonunique retained evidence construction"
        )
    construction = constructions[0]
    if construction.citation_id != citation_record_id or (
        construction.provenance_id != projection.provenance_record.record_id
    ):
        raise NativeGraphObservationProjectionError("substituted retained evidence pair")
    return construction


def _provenance(
    record: ProvenanceRecord,
    *,
    records: Sequence[CanonicalGraphRecord],
    evidence_projections: Sequence[BootstrapNativeEvidenceProjectionV3],
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    compilation: BootstrapNativeOperationCompilationV3,
    effect_digests: tuple[str, ...],
    policy_fingerprints: tuple[str, ...],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> ProvenanceStreamRecord:
    if record.source_id != authority.source_id:
        raise NativeGraphObservationProjectionError(
            "provenance source differs from planning authority"
        )
    projection = _unique_evidence_projection(
        evidence_projections, provenance_record_id=record.provenance_id,
    )
    construction = _retained_evidence_construction(
        authority, projection, citation_record_id=projection.citation_record.record_id,
    )
    citations = tuple(
        value for value in records
        if isinstance(value, CitationRecord) and value.citation_id == projection.citation_record.record_id
    )
    if len(citations) != 1:
        raise NativeGraphObservationProjectionError(
            "nonunique retained provenance citation pairing"
        )
    target = _cited_target(records, citations[0].cited_record_id)
    payload = _emit(ObservedProvenanceRecord(
        provenance_id=record.provenance_id,
        record_kind=target.record_kind, record_id=citations[0].cited_record_id,
        source_ids=(record.source_id,), operation_ids=(record.operation_id,),
        proof_ancestry_ids=tuple(sorted({
            compilation.compilation_digest,
            authority.authority_digest,
            authority.source_authority_evidence.evidence_digest,
            authority.source_authority_evidence.provenance_digest,
            construction.evidence_digest,
            projection.projection_digest,
            *effect_digests,
        })),
        policy_fingerprints=policy_fingerprints,
        system_interval=_system_interval(
            system_intervals, "provenance", record.provenance_id,
        ),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedProvenanceRecord", history, publication, limits)
    return ProvenanceStreamRecord(
        record_kind="provenance", primary_key=payload.provenance_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _retained_transition_construction(
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    record: TemporalTransitionRecord | IdentityLineageRecord,
) -> BootstrapNativeTemporalConstructionV3:
    """The unique transition-role temporal construction owning this carrier.

    The carrier's own temporal decision binding is the exact join key: the
    retained authority must declare exactly one ``transition``-role
    construction carrying that same binding, and its accepted evidence must
    equal the carrier's.  A missing, duplicated or divergent construction is
    an ambiguous effective-time authority and denies.
    """
    binding = record.temporal_decision_binding
    if binding.temporal_role != "transition":
        raise NativeGraphObservationProjectionError(
            "transition record does not carry its transition temporal role"
        )
    matches = tuple(
        item for item in authority.temporal_constructions
        if item.temporal_role == "transition"
        and item.temporal_decision_binding == binding
    )
    if len(matches) != 1:
        raise NativeGraphObservationProjectionError(
            "transition lacks its unique retained transition temporal authority"
        )
    construction = matches[0]
    if construction.accepted_temporal_evidence != record.temporal_evidence:
        raise NativeGraphObservationProjectionError(
            "transition evidence differs from its retained temporal authority"
        )
    return construction


def _observed_effective_time(
    construction: BootstrapNativeTemporalConstructionV3,
) -> ObservedEffectiveTimeValue:
    """Copy the retained effective-time coordinate its evidence carries.

    The retained coordinate's discriminator must agree with the temporal
    evidence the binding actually carries: ``certified_text_time`` requires
    selected authenticated source-interval evidence, an authenticated
    reference time requires the binding's reference evidence, and a
    system-recorded-only coordinate requires neither.  Any disagreement is an
    ambiguous effective time and denies; the fields are then copied exactly.
    """
    coordinate = construction.effective_time
    binding = construction.temporal_decision_binding
    closure = binding.decision_closure
    selected = set(closure.selected_candidate_ids)
    has_interval_evidence = any(
        candidate.candidate_id in selected
        and candidate.authenticated_source_interval_evidence is not None
        for candidate in closure.candidates
    )
    has_reference_evidence = binding.reference_evidence is not None
    if isinstance(coordinate, CertifiedTextEffectiveTime):
        if not has_interval_evidence:
            raise NativeGraphObservationProjectionError(
                "transition effective-time evidence is ambiguous"
            )
        return ObservedCertifiedTextEffectiveTime(
            kind="certified_text_time", effective_at=coordinate.effective_at,
            evidence_spans=coordinate.evidence_spans,
            temporal_policy_fingerprint=coordinate.temporal_policy_fingerprint,
        )
    if isinstance(coordinate, AuthenticatedReferenceEffectiveTime):
        if not has_reference_evidence or coordinate.reference_evidence != binding.reference_evidence:
            raise NativeGraphObservationProjectionError(
                "transition effective-time evidence is ambiguous"
            )
        return ObservedAuthenticatedReferenceEffectiveTime(
            kind="authenticated_reference_time", effective_at=coordinate.effective_at,
            reference_evidence=coordinate.reference_evidence,
            temporal_policy_fingerprint=coordinate.temporal_policy_fingerprint,
        )
    if isinstance(coordinate, SystemRecordedEffectiveTime):
        if has_interval_evidence or has_reference_evidence:
            raise NativeGraphObservationProjectionError(
                "transition effective-time evidence is ambiguous"
            )
        return ObservedSystemRecordedEffectiveTime(
            kind="system_recorded_only",
            temporal_policy_fingerprint=coordinate.temporal_policy_fingerprint,
        )
    raise NativeGraphObservationProjectionError(
        "transition effective-time coordinate is not a retained authority"
    )


def _transition_target_claim_ids(
    bindings: Sequence[BootstrapNativeTargetBindingV3], *, role: str,
) -> tuple[str, ...]:
    """The exact claim ids this arm's corrected/retracted targets retain."""
    ids = []
    for binding in bindings:
        if binding.role != role:
            continue
        if binding.authority.target.record_kind != "claim_assertion":
            raise NativeGraphObservationProjectionError(
                "transition target authority is not a claim assertion"
            )
        ids.append(binding.authority.target.record_id)
    if len(ids) != len(set(ids)):
        raise NativeGraphObservationProjectionError(
            "transition target authority is ambiguous"
        )
    return tuple(sorted(ids))


def _transition_claim_slot_key(
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    claims: Sequence[ClaimAssertion],
):
    """The retained claim slot authority of one transition.

    A correction retains its replacement claim identity, whose assertion slot
    is the exact slot the transition corrects.  A retraction retains no claim
    identity at all: its retracted target is only a claim reference and its
    proposal fact carries mention digests, so no retained carrier supplies a
    slot key and the transition is a typed refusal, never a guessed slot.
    """
    if isinstance(accepted_effect, BootstrapNativeCorrectionEffectV3):
        if len(claims) != 1:
            raise NativeGraphObservationProjectionError(
                "correction transition lacks its retained claim slot key authority"
            )
        identity = claims[0].claim_identity
        if identity is None:
            raise NativeGraphObservationProjectionError(
                "correction transition lacks its retained claim slot key authority"
            )
        return identity.assertion_key_at_recording.slot
    raise NativeGraphObservationProjectionError(
        "retraction transition lacks its retained claim slot key authority"
    )


def _temporal_transition(
    record: TemporalTransitionRecord,
    *,
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    claims: Sequence[ClaimAssertion],
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> TemporalTransitionStreamRecord:
    """Project one retained temporal transition of a correction/retraction arm."""
    if isinstance(accepted_effect, BootstrapNativeCorrectionEffectV3):
        expected_kind = "correction"
    elif isinstance(accepted_effect, BootstrapNativeRetractionEffectV3):
        expected_kind = "retraction"
    else:
        raise NativeGraphObservationProjectionError(
            "temporal transition is retained by an operation arm that does not own it"
        )
    if record.transition_kind != expected_kind:
        raise NativeGraphObservationProjectionError(
            "transition kind differs from its operation arm"
        )
    construction = _retained_transition_construction(authority, record)
    slot_key = _transition_claim_slot_key(accepted_effect, claims)
    if isinstance(accepted_effect, BootstrapNativeCorrectionEffectV3):
        compared = _transition_target_claim_ids(
            accepted_effect.corrected_targets, role="corrected_target",
        )
        if len(claims) != 1:
            raise NativeGraphObservationProjectionError(
                "correction transition lacks its next projection claim authority"
            )
        next_ids: tuple[str, ...] = (claims[0].claim_assertion_id,)
    else:
        compared = _transition_target_claim_ids(
            accepted_effect.retracted_targets, role="retracted_target",
        )
        next_ids = ()
    payload = _emit(ObservedTemporalTransition(
        transition_id=record.transition_id,
        operation_id=record.operation_id,
        claim_slot_key=slot_key,
        compared_claim_ids=compared,
        previous_projection_claim_ids=compared,
        next_projection_claim_ids=next_ids,
        transition_kind=record.transition_kind,
        effective_time=_observed_effective_time(construction),
        transition_temporal_evidence=record.temporal_evidence,
        transition_temporal_decision_binding=record.temporal_decision_binding,
        system_interval=_system_interval(
            system_intervals, "temporal_transition", record.transition_id,
        ),
        source_ids=(authority.source_id,),
        provenance_ids=tuple(sorted({
            provenance.provenance_id
            for citation, provenance in evidence_pairs
            if citation.cited_record_id == record.transition_id
        })),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedTemporalTransition", history, publication, limits)
    return TemporalTransitionStreamRecord(
        record_kind="temporal_transition", primary_key=payload.transition_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _action_supporting_claim_ids(
    claims: Sequence[ClaimAssertion],
    projections: Sequence[ClaimProjection],
) -> tuple[str, ...]:
    """Claims exactly paired through a retained claim projection, if any."""
    ids = []
    for claim in claims:
        matches = tuple(
            projection for projection in projections
            if projection.claim_assertion_id == claim.claim_assertion_id
        )
        if len(matches) != 1:
            raise NativeGraphObservationProjectionError(
                "ambiguous action claim pairing"
            )
        ids.append(claim.claim_assertion_id)
    return tuple(sorted(ids))


def _action_role_entities(
    accepted_effect: BootstrapNativeActionStateEffectV3,
    *,
    role_id: str,
    participants: Sequence[BootstrapProposalActionRoleParticipantV3],
    member_digest: str,
    lookup: Mapping[str, str],
) -> tuple[ObservedEntityReference, ...]:
    """Resolve one action role's participants to their exact entity targets.

    Each participant is joined by recomputing its retained mention coordinate
    -- the same digest the planner computes over the member digest, the role
    participant path and the mention digest -- against the arm's resolved
    participant bindings.  A participant with no unique entity target denies.
    """
    entities = []
    for index, participant in enumerate(participants):
        coordinate = contract_digest(
            b"memorii.bootstrap-graph.cluster-reference-coordinate.v3",
            {
                "operation_member_digest": member_digest,
                "path": f"action.{role_id}.{index}",
                "mention_digest": participant.mention_digest,
            },
        )
        matches = tuple(
            binding for binding in accepted_effect.resolved_participants
            if binding.role == "action_participant"
            and binding.source_coordinate_digest == coordinate
        )
        if len(matches) != 1 or matches[0].authority.target.record_kind != "entity_revision":
            raise NativeGraphObservationProjectionError(
                "action role participant does not resolve to one exact entity target"
            )
        entities.append(_entity_reference(
            lookup, matches[0].authority.target.record_id,
            reference_path=_ACTION_ROLE_PARTICIPANT_REFERENCE_PATH,
        ))
    return tuple(entities)


def _action_revision(
    record: ActionRevision,
    *,
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    claims: Sequence[ClaimAssertion],
    records: Sequence[BaseModel],
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    compilation: BootstrapNativeOperationCompilationV3,
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
    lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> ActionRevisionStreamRecord:
    """Project one retained action revision of an action-state arm."""
    if not isinstance(accepted_effect, BootstrapNativeActionStateEffectV3):
        raise NativeGraphObservationProjectionError(
            "action revision is retained by an operation arm that does not own it"
        )
    transition = authority.action_transition
    if transition is None:
        raise NativeGraphObservationProjectionError(
            "action revision lacks its retained action transition authority"
        )
    action_state = accepted_effect.action_state
    if transition.applicability_key.to_state_id != action_state.state_id:
        raise NativeGraphObservationProjectionError(
            "action transition applicability does not bind the retained action state"
        )
    if transition.action_policy_fingerprint != authority.action_policy_fingerprint:
        raise NativeGraphObservationProjectionError(
            "action transition authority policy is substituted"
        )
    member_digest = compilation.operation_input.operation_subject.member_digest
    projections = tuple(
        value for value in records if isinstance(value, ClaimProjection)
    )
    payload = _emit(ObservedActionRevision(
        action_revision_id=record.action_revision_id,
        logical_action_id=action_state.logical_action_digest,
        role_bindings=tuple(
            ObservedActionRoleBinding(
                role_id=binding.role_id,
                endpoint_kind=binding.endpoint_kind,
                entities=_action_role_entities(
                    accepted_effect, role_id=binding.role_id,
                    participants=binding.participants,
                    member_digest=member_digest, lookup=lookup,
                ),
            )
            for binding in action_state.role_bindings
        ),
        action_state=action_state.state_id,
        execution_branch_id=action_state.execution_branch_digest,
        transition_rule_id=transition.transition_rule_id,
        transition_applicability_key_digest=(
            transition.applicability_key.applicability_key_digest
        ),
        supporting_claim_assertion_ids=_action_supporting_claim_ids(claims, projections),
        valid_interval=record.valid_interval,
        authenticated_source_interval_evidence=_interval_evidence(record),
        temporal_decision_binding=record.temporal_decision_binding,
        system_interval=_system_interval(
            system_intervals, "action_revision", record.action_revision_id,
        ),
        source_ids=(authority.source_id,),
        provenance_ids=tuple(sorted({
            provenance.provenance_id
            for citation, provenance in evidence_pairs
            if citation.cited_record_id == record.action_revision_id
        })),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedActionRevision", history, publication, limits)
    return ActionRevisionStreamRecord(
        record_kind="action_revision", primary_key=payload.action_revision_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _identity_transition(
    record: IdentityLineageRecord,
    *,
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    authority: BootstrapNativePlanningConstructionAuthorityV3,
    retained_spans: Sequence[SourceSpanReference],
    lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> IdentityTransitionStreamRecord:
    """Project one retained identity lineage record of an identity arm."""
    if not isinstance(accepted_effect, BootstrapNativeIdentityEffectV3):
        raise NativeGraphObservationProjectionError(
            "identity lineage is retained by an operation arm that does not own it"
        )
    if authority.identity_construction is None:
        raise NativeGraphObservationProjectionError(
            "identity arm lacks its retained identity construction"
        )
    construction = _retained_transition_construction(authority, record)
    transition = record.transition
    payload = _emit(ObservedIdentityTransition(
        transition_id=record.identity_lineage_id,
        operation=transition.operation,
        predecessor_entities=tuple(
            _entity_reference(
                lookup, item.entity_revision_id,
                reference_path=_IDENTITY_PREDECESSOR_REFERENCE_PATH,
                logical_entity_id=item.logical_entity_id,
            )
            for item in transition.predecessors
        ),
        successor_entities=tuple(
            _entity_reference(
                lookup, item.entity_revision_id,
                reference_path=_IDENTITY_SUCCESSOR_REFERENCE_PATH,
                logical_entity_id=item.logical_entity_id,
            )
            for item in transition.successors
        ),
        effective_time=_observed_effective_time(construction),
        transition_temporal_evidence=record.temporal_evidence,
        transition_temporal_decision_binding=record.temporal_decision_binding,
        system_interval=_system_interval(
            system_intervals, "identity_lineage", record.identity_lineage_id,
        ),
        source_evidence=tuple(
            _resolve_complete_source_span(
                retained_spans, source_id=item.source_id, start=item.start, end=item.end,
            )
            for item in transition.source_evidence
        ),
        operation_id=record.operation_id,
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedIdentityTransition", history, publication, limits)
    return IdentityTransitionStreamRecord(
        record_kind="identity_transition", primary_key=payload.transition_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _reference_disposition(
    record: ReferenceDispositionRecord,
    *,
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    records: Sequence[CanonicalGraphRecord],
    lookup: Mapping[str, str],
    system_intervals: Mapping[tuple[str, str], TimeInterval],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> ReferenceDispositionStreamRecord:
    """Project one retained reference disposition of an identity arm."""
    if not isinstance(accepted_effect, BootstrapNativeIdentityEffectV3):
        raise NativeGraphObservationProjectionError(
            "reference disposition is retained by an operation arm that does not own it"
        )
    lineage = tuple(
        value for value in records if isinstance(value, IdentityLineageRecord)
    )
    if len(lineage) != 1:
        raise NativeGraphObservationProjectionError(
            "reference disposition lacks its unique retained identity lineage"
        )
    if len(record.successor_entity_revision_ids) != len(record.successor_logical_entity_ids):
        raise NativeGraphObservationProjectionError(
            "reference disposition successor shape is invalid"
        )
    payload = _emit(ObservedReferenceDisposition(
        disposition_id=record.reference_disposition_id,
        transition_id=lineage[0].identity_lineage_id,
        record_kind=record.target_record_kind,
        record_id=record.target_record_id,
        reference_path=record.target_reference_path,
        predecessor_entity=_entity_reference(
            lookup, record.predecessor_entity_revision_id,
            reference_path=_DISPOSITION_PREDECESSOR_REFERENCE_PATH,
            logical_entity_id=record.predecessor_logical_entity_id,
        ),
        successor_entities=tuple(
            _entity_reference(
                lookup, revision_id,
                reference_path=_DISPOSITION_SUCCESSOR_REFERENCE_PATH,
                logical_entity_id=logical_id,
            )
            for revision_id, logical_id in zip(
                record.successor_entity_revision_ids,
                record.successor_logical_entity_ids,
                strict=True,
            )
        ),
        disposition=record.disposition,
        evidence_ids=tuple(item.evidence_digest for item in record.source_evidence),
        system_interval=_system_interval(
            system_intervals, "reference_disposition", record.reference_disposition_id,
        ),
        boundary=False,
        record_digest="0" * 64,
    ), "ObservedReferenceDisposition", history, publication, limits)
    return ReferenceDispositionStreamRecord(
        record_kind="reference_disposition", primary_key=payload.disposition_id,
        record_digest=payload.record_digest, payload=payload,
    )


__all__ = [
    "NativeGraphObservationProjectionError",
    "NativeGraphObservationStreamRecord",
    "project_boundary_entity_revision",
    "project_native_graph_observation_stream",
]
