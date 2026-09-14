"""Nonproduction feasibility of public graph-observation field derivation.

Not the runtime materializer; certifies no provider or public endpoint.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from memorii.core.memory_evolution.graph_records import (
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    ProvenanceRecord,
    RelationRevision,
    TypeEvidence,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    CanonicalTypedValueProfileBinding,
)
from memorii.core.memory_evolution.semantic_state import LineageEvidenceReference
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_evolution.typed_value_artifact_integrity import (
    registered_self_digest_preimage,
)
from memorii.core.memory_evolution.typed_value_declarations import SelfDigestPolicy
from memorii.core.semantic_ingestion.contracts import (
    ClaimAssertion,
    SourceSpanReference,
)
from memorii.core.semantic_ingestion.event_replay import (
    EventBatchLogPosition,
    SemanticMemoryEvent,
)

PROJECTION_IDENTITY_DOMAIN = "memorii.semantic_ingestion.observation.ProjectionObservationIdentity.v1"

# The real profile identifier fixed by the typed-value profile binding owner
# (memorii/core/memory_evolution/ingestion_contracts.py: _PROFILE_ID). The
# remaining binding coordinates are explicit feasibility placeholders that
# satisfy the same all-hex/nonempty validation the registered root demands;
# promotion must replace them with the authored publication coordinates.
_IDENTITY_BINDING = CanonicalTypedValueProfileBinding(
    "semantic_ingestion_typed_value",
    1,
    "1" * 64,
    "feasibility.ProjectionObservationIdentity.v1",
    1,
    "2" * 64,
)
_IDENTITY_POLICY = SelfDigestPolicy("self_digest", "observation_id", PROJECTION_IDENTITY_DOMAIN)


class GraphObservationFeasibilityError(ValueError):
    """The retained native authority cannot derive one exact observation field."""


@dataclass(frozen=True)
class OperationSourceAuthority:
    """Verified source identity of one exact creating/updating native operation.

    Built only from the retained planning construction authority; never from
    caller-supplied coordinates.
    """

    operation_id: str
    source_ids: tuple[str, ...]


def native_operation_source_authority(compilation: object) -> OperationSourceAuthority:
    """Read the exact operation/source pair from the retained native authority.

    The planning construction authority is the retained carrier that binds one
    operation to its source; a missing or foreign authority denies.
    """
    operation_input = getattr(compilation, "operation_input", None)
    authority = getattr(operation_input, "planning_construction_authority", None)
    if authority is None:
        raise GraphObservationFeasibilityError("no retained planning construction authority")
    if getattr(authority, "operation_id", None) != getattr(compilation, "operation_id", None):
        raise GraphObservationFeasibilityError("planning authority does not bind this operation")
    source_id = getattr(authority, "source_id", None)
    if not isinstance(source_id, str) or not source_id:
        raise GraphObservationFeasibilityError("planning authority lacks its exact source")
    return OperationSourceAuthority(operation_id=authority.operation_id, source_ids=(source_id,))


@dataclass(frozen=True)
class ProjectedEntityFields:
    """Public entity-observation fields derived from retained native authority."""

    canonical_type: str | None
    valid_interval: None
    lifecycle_state: str
    source_ids: tuple[str, ...]
    operation_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProjectedRelationFields:
    """Public relation-observation fields derived from retained native authority."""

    supporting_claim_assertion_ids: tuple[str, ...]
    valid_interval: TimeInterval | None
    lifecycle_state: str
    source_ids: tuple[str, ...]
    provenance_ids: tuple[str, ...]


@dataclass(frozen=True)
class DerivedSystemInterval:
    """System interval derived from verified commit-event ownership."""

    interval: TimeInterval
    successor_event_id: str | None
    bounded: bool


def project_entity_fields(
    entity_revision: EntityRevision,
    type_evidence: Sequence[TypeEvidence],
    *,
    creating_operation: OperationSourceAuthority,
) -> ProjectedEntityFields:
    """Derive public entity fields as a fail-closed read of retained authority.

    canonical_type is the unique independently retained TypeEvidence
    asserted_type bound to this exact entity revision id. No eligible
    evidence means None; competing distinct types deny the cohort.
    valid_interval is always None: a structural entity revision has no
    native business-time interval. Grounded-mention type evidence cannot
    bind one exact entity revision and never contributes here.
    source_ids are the retained lineage references plus the exact
    creating/updating native operation's source, supplied only through a
    verified OperationSourceAuthority; a foreign operation denies.
    """
    if creating_operation.operation_id != entity_revision.operation_id:
        raise GraphObservationFeasibilityError("entity revision differs from its creating operation authority")
    asserted: set[str] = set()
    for evidence in type_evidence:
        reference = evidence.entity_reference
        if not isinstance(reference, CanonicalEntityRevisionRef):
            continue
        if reference.entity_revision_id != entity_revision.entity_revision_id:
            continue
        if reference.logical_entity_id != entity_revision.logical_entity_id:
            raise GraphObservationFeasibilityError("entity type evidence binds a foreign logical entity")
        asserted.add(evidence.asserted_type)
    if len(asserted) > 1:
        raise GraphObservationFeasibilityError("competing entity type evidence")
    source_ids = {
        item.source_id for item in entity_revision.source_evidence
    } | set(creating_operation.source_ids)
    return ProjectedEntityFields(
        canonical_type=next(iter(asserted)) if asserted else None,
        valid_interval=None,
        lifecycle_state=entity_revision.lifecycle,
        source_ids=tuple(sorted(source_ids)),
        operation_ids=(entity_revision.operation_id,),
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


def _claim_payload_binds_projection(claim: ClaimAssertion, projection: ClaimProjection) -> bool:
    """Canonical payload equality between the claim and its projection join.

    The claim's retained AcceptedClaimIdentity is the canonical payload
    carrier: its assertion key must agree with the projection's endpoint
    binding. A claim without a retained identity cannot prove payload
    equality and never becomes supporting.
    """
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
    relation_revision: RelationRevision,
    claim_assertions: Sequence[ClaimAssertion],
    claim_projections: Sequence[ClaimProjection],
) -> tuple[ClaimAssertion, ...]:
    supporting = []
    for claim in claim_assertions:
        predicate_id = _claim_predicate_id(claim)
        if predicate_id is None:
            continue
        if any(
            projection.claim_assertion_id == claim.claim_assertion_id
            and _projection_binds_relation(projection, relation_revision, predicate_id)
            and _claim_payload_binds_projection(claim, projection)
            for projection in claim_projections
        ):
            supporting.append(claim)
    supporting_ids = [claim.claim_assertion_id for claim in supporting]
    if len(set(supporting_ids)) != len(supporting_ids):
        raise GraphObservationFeasibilityError("ambiguous relation claim pairing")
    return tuple(supporting)


def unrelated_same_predicate_claims(
    relation_revision: RelationRevision,
    claim_assertions: Sequence[ClaimAssertion],
    claim_projections: Sequence[ClaimProjection],
) -> tuple[str, ...]:
    """Separation hook: claims sharing the predicate but not the exact endpoints.

    These are exactly the claims a same-predicate search would wrongly admit.
    """
    return tuple(
        claim.claim_assertion_id
        for claim in claim_assertions
        if _claim_predicate_id(claim) == relation_revision.predicate_id
        and claim not in _supporting_claims(relation_revision, claim_assertions, claim_projections)
    )


def intersect_valid_intervals(
    intervals: Sequence[TimeInterval | None],
) -> TimeInterval | None:
    """Common interval of exact supporting claims; None means unbounded.

    An empty intersection denies the observation instead of inventing one.
    """
    if not intervals:
        raise GraphObservationFeasibilityError("relation has no exactly paired supporting claim")
    bounded = [item for item in intervals if item is not None]
    if not bounded:
        return None
    start = max(item.start for item in bounded)
    ends = [item.end for item in bounded if item.end is not None]
    end = min(ends) if ends else None
    if end is not None and end <= start:
        raise GraphObservationFeasibilityError("supporting claim interval disagreement")
    return TimeInterval(start=start, end=end)


def relation_provenance_ids(
    supporting_claim_assertion_ids: Sequence[str],
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]],
) -> tuple[str, ...]:
    """Provenance pairs whose citations target the exact supporting claims.

    A provenance record whose citation targets the relation itself, an
    unrelated claim or any other record is never reinterpreted as
    relation-targeted and never contributes.
    """
    supporting = set(supporting_claim_assertion_ids)
    return tuple(sorted({
        provenance.provenance_id
        for citation, provenance in evidence_pairs
        if citation.cited_record_id in supporting
    }))


def project_relation_fields(
    relation_revision: RelationRevision,
    claim_assertions: Sequence[ClaimAssertion],
    claim_projections: Sequence[ClaimProjection],
    evidence_pairs: Sequence[tuple[CitationRecord, ProvenanceRecord]] = (),
) -> ProjectedRelationFields:
    """Derive public relation fields from the exact native claim pairing.

    Supporting claims are exactly the claims whose ClaimProjection binds this
    relation's exact subject revision, object revision and predicate with
    canonical payload equality through the claim's retained identity. No
    same-predicate unrelated search happens. provenance_ids carry only the
    provenance pairs whose citations target those exact supporting claims.
    """
    supporting = _supporting_claims(relation_revision, claim_assertions, claim_projections)
    if not supporting:
        raise GraphObservationFeasibilityError("relation has no exactly paired supporting claim")
    interval = intersect_valid_intervals([claim.valid_interval for claim in supporting])
    source_ids = {
        claim.source_authority_evidence.source_id
        for claim in supporting
        if claim.source_authority_evidence is not None
    }
    supporting_ids = tuple(claim.claim_assertion_id for claim in supporting)
    return ProjectedRelationFields(
        supporting_claim_assertion_ids=tuple(sorted(supporting_ids)),
        valid_interval=interval,
        lifecycle_state="active",
        source_ids=tuple(sorted(source_ids)),
        provenance_ids=relation_provenance_ids(supporting_ids, evidence_pairs),
    )


def derive_system_interval(
    events_with_positions: Sequence[tuple[SemanticMemoryEvent, EventBatchLogPosition]],
    *,
    record_id: str,
    record_digest: str | None = None,
) -> DerivedSystemInterval:
    """Derive the system interval of one exact record version from events.

    Event (timestamp, sequence) is the ordering authority: same-time
    successors are ordered by sequence. The interval starts at the owning
    event's timestamp and ends at the successor event's timestamp when
    that end is strictly later; a same-time successor cannot be a closed
    TimeInterval (whose end must be later than its start), so the
    interval end stays None while successor_event_id retains the exact
    lineage. Zero owning events or any ambiguity denies.
    """
    events_with_positions = tuple(events_with_positions)
    order_keys = [(event.timestamp, position.sequence) for event, position in events_with_positions]
    if len(set(order_keys)) != len(order_keys):
        raise GraphObservationFeasibilityError("ambiguous event ordering")
    owning = [
        (event, position)
        for event, position in events_with_positions
        if event.payload.record_id == record_id and event.payload.entity_id == record_id
    ]
    if not owning:
        raise GraphObservationFeasibilityError("no owning commit event")
    if record_digest is not None:
        selected = [
            (event, position) for event, position in owning
            if event.payload.record_digest == record_digest
        ]
    else:
        selected = owning
    if len(selected) > 1:
        raise GraphObservationFeasibilityError("ambiguous owning commit event")
    if not selected:
        raise GraphObservationFeasibilityError("no owning commit event")
    own_event, _own_position = selected[0]
    own_key = own_event.timestamp, next(
        position.sequence for event, position in events_with_positions if event is own_event
    )
    successors = [
        event for event, _position in events_with_positions
        if event.payload.prior_record_digest == own_event.payload.record_digest
        and event.payload.record_kind == own_event.payload.record_kind
        and event.payload.record_id == own_event.payload.record_id
    ]
    if len(successors) > 1:
        raise GraphObservationFeasibilityError("ambiguous event successor")
    if successors:
        successor = successors[0]
        successor_key = successor.timestamp, next(
            position.sequence for event, position in events_with_positions if event is successor
        )
        if successor_key <= own_key:
            raise GraphObservationFeasibilityError("ambiguous event ordering")
        bounded = successor.timestamp > own_event.timestamp
        return DerivedSystemInterval(
            interval=TimeInterval(
                start=own_event.timestamp,
                end=successor.timestamp if bounded else None,
            ),
            successor_event_id=successor.event_id,
            bounded=bounded,
        )
    return DerivedSystemInterval(
        interval=TimeInterval(start=own_event.timestamp, end=None),
        successor_event_id=None,
        bounded=False,
    )


def resolve_complete_source_span(
    candidate_spans: Sequence[SourceSpanReference],
    reference: LineageEvidenceReference,
) -> SourceSpanReference:
    """Copy the uniquely matched complete retained SourceSpanReference.

    A LineageEvidenceReference carries only source_id/start/end plus an
    evidence digest with no SourceSpanReference counterpart, so it can be
    joined only by source identity and exact segment-local coordinates.
    The artifact and mapping proof are copied from the matched retained
    record, never manufactured.
    """
    matches = tuple(
        span for span in candidate_spans
        if span.source_id == reference.source_id
        and span.segment_local_span.start == reference.start
        and span.segment_local_span.end == reference.end
    )
    if not matches:
        raise GraphObservationFeasibilityError("no complete retained source span")
    if len(matches) > 1:
        raise GraphObservationFeasibilityError("ambiguous retained source span")
    return matches[0]


def lineage_reference_cannot_manufacture_span(reference: LineageEvidenceReference) -> SourceSpanReference:
    """Proof helper: a lineage reference alone is insufficient by construction.

    No SourceSpanReference may be produced from source_id/start/end alone;
    the retained artifact and mapping proof have no lineage counterpart.
    """
    raise GraphObservationFeasibilityError(
        "lineage evidence reference cannot manufacture a complete source span"
    )


def _identity_tree(
    projection_kind: str,
    repository_id: str,
    generation_digest: str,
    projection_digest: str,
    observation_id: str,
) -> dict[str, object]:
    return {
        "$type": "map",
        "entries": tuple(sorted((
            ("generation_digest", generation_digest),
            ("projection_digest", projection_digest),
            ("projection_kind", projection_kind),
            ("repository_id", repository_id),
            ("observation_id", observation_id),
        ))),
    }


_LOWER_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _validate_identity_fields(
    projection_kind: str,
    repository_id: str,
    generation_digest: str,
    projection_digest: str,
) -> None:
    """Fail closed on any nonconforming identity preimage field."""
    if projection_kind not in ("temporal", "trust"):
        raise GraphObservationFeasibilityError("projection identity kind is not temporal or trust")
    if not isinstance(repository_id, str) or not repository_id:
        raise GraphObservationFeasibilityError("projection identity repository is empty")
    for name, digest in (
        ("generation", generation_digest),
        ("projection", projection_digest),
    ):
        if not isinstance(digest, str) or not _LOWER_HEX64.fullmatch(digest):
            raise GraphObservationFeasibilityError(f"projection identity {name} digest is not lowercase sha256")


def projection_observation_identity(
    projection_kind: Literal["temporal", "trust"],
    repository_id: str,
    generation_digest: str,
    projection_digest: str,
) -> str:
    """Derive the ProjectionObservationIdentity.v1 self-digest identity.

    The complete selected binding and the four ordinary fields are the
    preimage; observation_id excludes only itself, exactly as the existing
    owner prescribes. Nonconforming field values deny before any digest.
    """
    _validate_identity_fields(projection_kind, repository_id, generation_digest, projection_digest)
    _IDENTITY_BINDING.validate()
    tree = _identity_tree(
        projection_kind, repository_id, generation_digest, projection_digest, "",
    )
    preimage = registered_self_digest_preimage(
        tree, binding=_IDENTITY_BINDING, policy=_IDENTITY_POLICY,
    )
    return sha256(preimage).hexdigest()


def verify_projection_observation_identity(
    projection_kind: Literal["temporal", "trust"],
    repository_id: str,
    generation_digest: str,
    projection_digest: str,
    observation_id: str,
) -> bool:
    """Re-derive the registered identity and compare it exactly."""
    return projection_observation_identity(
        projection_kind, repository_id, generation_digest, projection_digest,
    ) == observation_id
