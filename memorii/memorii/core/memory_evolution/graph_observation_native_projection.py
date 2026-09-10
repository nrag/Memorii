"""Registered projection of one verified retained native graph operation.

This owner converts exactly one already-verified accepted native operation
(the joined operation compilation, accepted effect, and complete retained
native record inventory) into observed graph-observation stream records.
It is a read-only view of retained authority: every field is copied or joined
from retained native records, the planning construction authority, or the
caller's verified evidence pairs.  No field is inferred from the caller,
current host policy, text, or model output, and no new stored graph
representation is created.

Every ambiguous or unprovable join fails closed with
:class:`NativeGraphObservationProjectionError` carrying a distinctive
message; a partial or guessed observed record is never emitted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, TypeAlias, TypeVar

from pydantic import BaseModel

from memorii.core.memory_evolution.graph_observation_records import (
    ObservedAliasRevision,
    ObservedAssertionEntityReference,
    ObservedCitationRecord,
    ObservedClaimAssertion,
    ObservedEntityReference,
    ObservedEntityRevision,
    ObservedProvenanceRecord,
    ObservedRelation,
    ObservedTypeEvidence,
)
from memorii.core.memory_evolution.graph_observation_streams import (
    AliasRevisionStreamRecord,
    CitationStreamRecord,
    ClaimAssertionStreamRecord,
    EntityRevisionStreamRecord,
    ProvenanceStreamRecord,
    RelationStreamRecord,
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
    BootstrapProposalFactV3,
    ClaimAssertion,
    SourceSpanReference,
    TypedLiteral,
)

if TYPE_CHECKING:
    from memorii.core.memory_evolution.graph_records import CanonicalGraphRecord


class NativeGraphObservationProjectionError(ValueError):
    """The retained native authority cannot produce one exact observation."""


NativeGraphObservationStreamRecord: TypeAlias = (
    EntityRevisionStreamRecord
    | AliasRevisionStreamRecord
    | TypeEvidenceStreamRecord
    | ClaimAssertionStreamRecord
    | RelationStreamRecord
    | CitationStreamRecord
    | ProvenanceStreamRecord
)

_Observed = TypeVar(
    "_Observed",
    ObservedEntityRevision,
    ObservedAliasRevision,
    ObservedTypeEvidence,
    ObservedClaimAssertion,
    ObservedRelation,
    ObservedCitationRecord,
    ObservedProvenanceRecord,
)

# Retained record kinds this projection can convert into observed records.
# ``claim_projection`` is a join helper for relation pairing and is not
# emitted; every other kind maps to exactly one observed stream family.
_SUPPORTED_RECORD_KINDS = frozenset({
    "entity_revision", "alias_revision", "type_evidence", "claim_assertion",
    "claim_projection", "relation_revision", "citation", "provenance",
})


def project_native_graph_observation_stream(
    *,
    compilation: BootstrapNativeOperationCompilationV3,
    accepted_effect: BootstrapNativeAcceptedOperationEffectV3,
    retained_native_records: Sequence[CanonicalGraphRecord],
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
    commit_values: PlanningCommitValues,
    authorizing_transaction_group_id: str,
    native_entity_lookup: Mapping[str, ObservedEntityReference],
    boundary_ids: frozenset[str],
    system_interval: TimeInterval,
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
    observation runtime to obtain its real record digest.
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

    claims = [value for value in records if isinstance(value, ClaimAssertion)]
    if len(claims) != 1:
        raise NativeGraphObservationProjectionError(
            "accepted operation arm does not retain exactly one claim assertion"
        )
    claim = claims[0]
    type_evidence_cohort = tuple(
        value for value in retained_native_records if isinstance(value, TypeEvidence)
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
                authority_source_id=authority.source_id, system_interval=system_interval,
                boundary_ids=boundary_ids, history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, AliasRevision):
            emitted.append(_alias_revision(
                value, lookup=native_entity_lookup, authority_source_id=authority.source_id,
                system_interval=system_interval, boundary_ids=boundary_ids,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, TypeEvidence):
            emitted.append(_type_evidence(
                value, retained_spans=retained_spans, lookup=native_entity_lookup,
                system_interval=system_interval, boundary_ids=boundary_ids,
                history=history, publication=publication, limits=limits,
            ))
    claim_record = _claim(
        claim, fact, evidence_pairs=evidence_pairs, policy_fingerprints=policy_fingerprints,
        lookup=native_entity_lookup, system_interval=system_interval, boundary_ids=boundary_ids,
        history=history, publication=publication, limits=limits,
    )
    emitted.append(claim_record)
    for value in records:
        if isinstance(value, RelationRevision):
            emitted.append(_relation(
                value, claim, records=records, evidence_pairs=evidence_pairs,
                lookup=native_entity_lookup, system_interval=system_interval,
                boundary_ids=boundary_ids, history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, CitationRecord):
            emitted.append(_citation(
                value, records=records, evidence_projections=evidence_projections,
                authority=authority, system_interval=system_interval, boundary_ids=boundary_ids,
                history=history, publication=publication, limits=limits,
            ))
        elif isinstance(value, ProvenanceRecord):
            emitted.append(_provenance(
                value, records=records, evidence_projections=evidence_projections,
                authority=authority, compilation=compilation, effect_digests=effect_digests,
                policy_fingerprints=policy_fingerprints, system_interval=system_interval,
                boundary_ids=boundary_ids, history=history, publication=publication, limits=limits,
            ))
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
        return effect.evidence_projections, effect.transition_records, (effect.effect_digest,), None
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
    lookup: Mapping[str, ObservedEntityReference],
    entity_revision_id: str,
    *,
    logical_entity_id: str | None = None,
) -> ObservedEntityReference:
    reference = lookup.get(entity_revision_id)
    if reference is None or reference.entity_revision_id != entity_revision_id or (
        logical_entity_id is not None and reference.logical_entity_id != logical_entity_id
    ):
        raise NativeGraphObservationProjectionError("native entity lookup is incomplete")
    return reference


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
    lookup: Mapping[str, ObservedEntityReference],
    authority_source_id: str,
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
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
        system_interval=system_interval,
        source_ids=tuple(sorted({
            item.source_id for item in record.source_evidence
        } | {authority_source_id})),
        operation_ids=(record.operation_id,),
        boundary=record.entity_revision_id in boundary_ids,
        record_digest="0" * 64,
    ), "ObservedEntityRevision", history, publication, limits)
    return EntityRevisionStreamRecord(
        record_kind="entity_revision", primary_key=payload.entity_revision_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _alias_revision(
    record: AliasRevision,
    *,
    lookup: Mapping[str, ObservedEntityReference],
    authority_source_id: str,
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
    history: ProtectedTypedValueRegistryHistory,
    publication: VerifiedTypedValuePublication,
    limits: ProtectedTypedValueArtifactReaderLimits,
) -> AliasRevisionStreamRecord:
    reference = _lookup_reference(lookup, record.entity_revision_id)
    payload = _emit(ObservedAliasRevision(
        alias_revision_id=record.alias_revision_id, entity=reference,
        alias_namespace=record.alias_namespace,
        normalized_alias_key=record.normalized_alias_key,
        binding_evidence_ids=tuple(item.evidence_digest for item in record.source_evidence),
        valid_interval=None, system_interval=system_interval,
        source_ids=tuple(sorted({
            item.source_id for item in record.source_evidence
        } | {authority_source_id})),
        boundary=record.alias_revision_id in boundary_ids,
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
    lookup: Mapping[str, ObservedEntityReference],
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
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
    entity = _lookup_reference(
        lookup, reference.entity_revision_id, logical_entity_id=reference.logical_entity_id,
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
        valid_interval=record.valid_interval, system_interval=system_interval,
        boundary=record.evidence_id in boundary_ids,
        record_digest="0" * 64,
    ), "ObservedTypeEvidence", history, publication, limits)
    return TypeEvidenceStreamRecord(
        record_kind="type_evidence", primary_key=payload.evidence_id,
        record_digest=payload.record_digest, payload=payload,
    )


def _interval_evidence(claim: ClaimAssertion):
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
    lookup: Mapping[str, ObservedEntityReference],
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
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
            entity=_lookup_reference(lookup, identity.object_assertion_ref.entity_revision_id),
            logical_entity_id_at_assertion=identity.object_assertion_ref.logical_entity_id_at_assertion,
        )
    citing = tuple(
        pair for pair in evidence_pairs
        if pair[0].cited_record_id == claim.claim_assertion_id
    )
    payload = _emit(ObservedClaimAssertion(
        claim_assertion_id=claim.claim_assertion_id,
        subject_assertion_ref=ObservedAssertionEntityReference(
            entity=_lookup_reference(lookup, subject.entity_revision_id),
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
        system_interval=system_interval,
        source_authority_class=authority_evidence.authority.authority_class,
        source_ids=(authority_evidence.source_id,),
        operation_ids=(claim.operation_id,),
        citation_ids=tuple(sorted({pair[0].citation_id for pair in citing})),
        provenance_ids=tuple(sorted({pair[1].provenance_id for pair in citing})),
        policy_fingerprints=policy_fingerprints,
        boundary=claim.claim_assertion_id in boundary_ids,
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
    lookup: Mapping[str, ObservedEntityReference],
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
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
        subject=_lookup_reference(
            lookup, record.subject_entity_revision_id,
            logical_entity_id=record.subject_logical_entity_id,
        ),
        object_kind="entity",
        object_entity=_lookup_reference(
            lookup, record.object_entity_revision_id,
            logical_entity_id=record.object_logical_entity_id,
        ),
        literal_value=None,
        supporting_claim_assertion_ids=tuple(sorted(supporting_ids)),
        lifecycle_state="active",
        valid_interval=_intersect_valid_intervals(
            [item.valid_interval for item in supporting]
        ),
        system_interval=system_interval,
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
        boundary=record.relation_revision_id in boundary_ids,
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
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
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
        boundary=record.citation_id in boundary_ids,
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
    system_interval: TimeInterval,
    boundary_ids: frozenset[str],
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
        system_interval=system_interval, boundary=record.provenance_id in boundary_ids,
        record_digest="0" * 64,
    ), "ObservedProvenanceRecord", history, publication, limits)
    return ProvenanceStreamRecord(
        record_kind="provenance", primary_key=payload.provenance_id,
        record_digest=payload.record_digest, payload=payload,
    )


__all__ = [
    "NativeGraphObservationProjectionError",
    "NativeGraphObservationStreamRecord",
    "project_native_graph_observation_stream",
]
