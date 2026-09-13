"""Real retained native fact arm proves the observation field recipes fail closed.

The production capture currently supplies a validated fact arm containing real
EntityRevision, ClaimAssertion, ClaimProjection and RelationRevision records;
system-interval, source-span and identity recipes use the same production
contracts. No provider or public endpoint is certified by these tests.
"""

from datetime import UTC, datetime

import pytest
from feasibility import (
    PROJECTION_IDENTITY_DOMAIN,
    GraphObservationFeasibilityError,
    OperationSourceAuthority,
    derive_system_interval,
    intersect_valid_intervals,
    lineage_reference_cannot_manufacture_span,
    native_operation_source_authority,
    project_entity_fields,
    project_relation_fields,
    projection_observation_identity,
    relation_provenance_ids,
    resolve_complete_source_span,
    unrelated_same_predicate_claims,
    verify_projection_observation_identity,
)
from memorii.core.memory_evolution.graph_planning import (
    PlanningCommitValues,
    materialize_canonical_planning_payload,
)
from memorii.core.memory_evolution.graph_records import (
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    GroundedMentionRef,
    ProvenanceRecord,
    RelationRevision,
    SourceAuthority,
    TypeEvidence,
    canonical_graph_codec_manifest,
)
from memorii.core.memory_evolution.semantic_state import LineageEvidenceReference
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativeFactEffectV3,
    ClaimAssertion,
    contract_digest,
)
from memorii.core.semantic_ingestion.event_replay import (
    EventBatchLogPosition,
    SemanticEventReplayError,
    SemanticMaterializedMemoryRecord,
    build_semantic_memory_event,
)
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import (
    _capture_builtin_fact_planning,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
)


@pytest.fixture(scope="module")
def captured_fact():
    patch = pytest.MonkeyPatch()
    try:
        return _capture_builtin_fact_planning(patch)
    finally:
        patch.undo()


def _materialized(effect, group_request):
    commit_values = PlanningCommitValues(
        transaction_group_id=group_request.transaction_group_id,
        graph_revision_before="feasibility-before",
        graph_revision_after="feasibility-after",
        committed_at=TEST_NOW,
    )
    return tuple(
        materialize_canonical_planning_payload(
            record.planning_payload,
            commit_values=commit_values,
            authorizing_transaction_group_id=group_request.transaction_group_id,
        )
        for record in effect.planning_records
    )


@pytest.fixture(scope="module")
def fact_records(captured_fact):
    _, _, group_request = captured_fact
    effect = group_request.ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    return _materialized(effect, group_request)


def _entity(records):
    return next(record for record in records if isinstance(record, EntityRevision))


def _relation(records):
    return next(record for record in records if isinstance(record, RelationRevision))


def _claim(records):
    return next(record for record in records if isinstance(record, ClaimAssertion))


def _projection(records):
    return next(record for record in records if isinstance(record, ClaimProjection))


def _type_evidence(entity_revision, asserted_type, *, logical_entity_id=None, grounded=False):
    codec = next(
        entry.codec_fingerprint for entry in canonical_graph_codec_manifest().entries
        if entry.record_kind == "type_evidence"
    )
    if grounded:
        reference = GroundedMentionRef(
            source_id="grounded-source", start=0, end=4, cluster_id="cluster:feasibility",
        )
    else:
        reference = CanonicalEntityRevisionRef(
            entity_revision_id=entity_revision.entity_revision_id,
            logical_entity_id=logical_entity_id or entity_revision.logical_entity_id,
        )
    return TypeEvidence.create(
        operation_id=entity_revision.operation_id,
        codec_fingerprint=codec,
        evidence_id=f"evidence:{asserted_type}",
        entity_reference=reference,
        asserted_type=asserted_type,
        origin="verified_graph_type_assertion",
        authority=SourceAuthority(
            authority_class="feasibility-authority",
            authenticated_provenance_class="feasibility-provenance",
            policy_revision="feasibility-policy-1",
        ),
        recorded_at=TEST_NOW,
        proof_policy_fingerprint="3" * 64,
    )


def _compilation(captured_fact):
    _, _, group_request = captured_fact
    return group_request.ordered_operation_inputs[0].reduction.native_compilation


def _effect(captured_fact):
    _, _, group_request = captured_fact
    return group_request.ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect


@pytest.fixture(scope="module")
def operation_authority(captured_fact):
    return native_operation_source_authority(_compilation(captured_fact))


def _evidence_pairs(captured_fact):
    _, _, group_request = captured_fact
    effect = _effect(captured_fact)
    commit_values = PlanningCommitValues(
        transaction_group_id=group_request.transaction_group_id,
        graph_revision_before="feasibility-before",
        graph_revision_after="feasibility-after",
        committed_at=TEST_NOW,
    )
    pairs = []
    for projection in effect.evidence_projections:
        citation = materialize_canonical_planning_payload(
            projection.citation_record.planning_payload,
            commit_values=commit_values,
            authorizing_transaction_group_id=group_request.transaction_group_id,
        )
        provenance = materialize_canonical_planning_payload(
            projection.provenance_record.planning_payload,
            commit_values=commit_values,
            authorizing_transaction_group_id=group_request.transaction_group_id,
        )
        assert isinstance(citation, CitationRecord) and isinstance(provenance, ProvenanceRecord)
        pairs.append((citation, provenance))
    return tuple(pairs)


def test_entity_sources_derive_from_verified_creating_operation(
    fact_records, operation_authority,
):
    entity = _entity(fact_records)
    assert operation_authority.operation_id == entity.operation_id
    fields = project_entity_fields(entity, (), creating_operation=operation_authority)
    assert fields.canonical_type is None
    assert fields.valid_interval is None
    assert fields.lifecycle_state == entity.lifecycle
    assert fields.source_ids == tuple(sorted(
        {item.source_id for item in entity.source_evidence}
        | set(operation_authority.source_ids)
    ))
    assert operation_authority.source_ids[0] in fields.source_ids
    assert fields.operation_ids == (entity.operation_id,)


def test_entity_foreign_creating_operation_denies(fact_records, operation_authority):
    entity = _entity(fact_records)
    foreign = OperationSourceAuthority(
        operation_id="foreign-operation", source_ids=("foreign-source",),
    )
    with pytest.raises(
        GraphObservationFeasibilityError, match="creating operation authority",
    ):
        project_entity_fields(entity, (), creating_operation=foreign)


def test_native_operation_source_authority_requires_retained_authority(captured_fact):
    compilation = _compilation(captured_fact)
    authority = native_operation_source_authority(compilation)
    assert authority.operation_id == compilation.operation_id
    stripped = compilation.model_copy(update={"operation_input": compilation.operation_input.model_copy(
        update={"planning_construction_authority": None},
    )})
    with pytest.raises(
        GraphObservationFeasibilityError, match="no retained planning construction authority",
    ):
        native_operation_source_authority(stripped)
    substituted = compilation.model_copy(update={"operation_id": "other-operation"})
    with pytest.raises(
        GraphObservationFeasibilityError, match="does not bind this operation",
    ):
        native_operation_source_authority(substituted)


def test_entity_canonical_type_requires_unique_compatible_type_evidence(
    fact_records, operation_authority,
):
    entity = _entity(fact_records)
    unique = project_entity_fields(
        entity, (_type_evidence(entity, "product"),), creating_operation=operation_authority,
    )
    assert unique.canonical_type == "product"
    compatible_duplicate = project_entity_fields(
        entity,
        (_type_evidence(entity, "product"), _type_evidence(entity, "product")),
        creating_operation=operation_authority,
    )
    assert compatible_duplicate.canonical_type == "product"
    other_entity = EntityRevision.create(
        entity_revision_id="other-revision",
        logical_entity_id=entity.logical_entity_id,
        operation_id=entity.operation_id,
        codec_fingerprint=entity.codec_fingerprint,
        source_evidence=entity.source_evidence,
    )
    unrelated = project_entity_fields(
        entity,
        (_type_evidence(other_entity, "product"), _type_evidence(other_entity, "person")),
        creating_operation=operation_authority,
    )
    assert unrelated.canonical_type is None
    grounded = project_entity_fields(
        entity,
        (_type_evidence(entity, "place", grounded=True),),
        creating_operation=operation_authority,
    )
    assert grounded.canonical_type is None


def test_entity_competing_type_evidence_denies(fact_records, operation_authority):
    entity = _entity(fact_records)
    with pytest.raises(GraphObservationFeasibilityError, match="competing entity type evidence"):
        project_entity_fields(
            entity,
            (_type_evidence(entity, "product"), _type_evidence(entity, "person")),
            creating_operation=operation_authority,
        )


def test_entity_foreign_logical_identity_type_evidence_denies(fact_records, operation_authority):
    entity = _entity(fact_records)
    with pytest.raises(GraphObservationFeasibilityError, match="foreign logical entity"):
        project_entity_fields(
            entity,
            (_type_evidence(entity, "product", logical_entity_id="other-logical"),),
            creating_operation=operation_authority,
        )


def _rebuild_claim(claim, *, claim_assertion_id=None, interval=None):
    body = claim.model_dump(mode="python", exclude={"record_digest"})
    if interval is not None:
        carrier_interval = {"start": interval.start, "end": interval.end}
        closure = body["temporal_evidence"]["decision_closure"]
        for candidate in closure["candidates"]:
            candidate["interval"] = carrier_interval
            evidence = candidate.get("authenticated_source_interval_evidence")
            if evidence is not None:
                evidence["interval"] = carrier_interval
                evidence_body = {
                    key: value for key, value in evidence.items() if key != "evidence_digest"
                }
                evidence["evidence_digest"] = contract_digest(
                    b"memorii.semantic-ingestion.source-interval-evidence.v1", evidence_body,
                )
            candidate_body = {
                key: value for key, value in candidate.items() if key != "candidate_digest"
            }
            candidate["candidate_digest"] = contract_digest(
                b"memorii.semantic-ingestion.temporal-candidate.v1", candidate_body,
            )
        closure["resolved_interval"] = carrier_interval
        closure_body = {key: value for key, value in closure.items() if key != "closure_digest"}
        closure["closure_digest"] = contract_digest(
            b"memorii.semantic-ingestion.temporal-decision-closure.v1", closure_body,
        )
        binding = body["temporal_decision_binding"]
        binding["decision_closure"] = closure
        binding_body = {key: value for key, value in binding.items() if key != "binding_digest"}
        binding["binding_digest"] = contract_digest(
            b"memorii.semantic-ingestion.temporal_decision_binding.v1", binding_body,
        )
        body["valid_interval"] = carrier_interval
    if claim_assertion_id is not None:
        body["claim_assertion_id"] = claim_assertion_id
    return ClaimAssertion.model_validate({
        **body,
        "record_digest": contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1", body,
        ),
    })


def test_relation_fields_pair_the_exact_native_claim(fact_records):
    relation = _relation(fact_records)
    claim = _claim(fact_records)
    projection = _projection(fact_records)
    assert projection.claim_assertion_id == claim.claim_assertion_id
    fields = project_relation_fields(relation, (claim,), (projection,))
    assert fields.supporting_claim_assertion_ids == (claim.claim_assertion_id,)
    assert fields.valid_interval == claim.valid_interval
    assert fields.lifecycle_state == "active"
    assert fields.source_ids == (claim.source_authority_evidence.source_id,)


def test_relation_provenance_ids_come_only_from_supporting_claim_citations(captured_fact):
    fact_records = _materialized(_effect(captured_fact), captured_fact[2])
    relation = _relation(fact_records)
    claim = _claim(fact_records)
    pairs = _evidence_pairs(captured_fact)
    claiming = tuple(
        (citation, provenance) for citation, provenance in pairs
        if citation.cited_record_id == claim.claim_assertion_id
    )
    assert claiming, "the retained fact capture cites the claim it projects"
    fields = project_relation_fields(
        relation, (claim,), (_projection(fact_records),), pairs,
    )
    assert fields.provenance_ids == tuple(sorted(
        provenance.provenance_id for _, provenance in claiming
    ))
    # A provenance pair whose citation targets the relation itself must not
    # be reinterpreted as relation-targeted provenance.
    relation_targeted_citation = claiming[0][0].model_copy(update={
        "cited_record_id": relation.relation_revision_id,
    })
    relation_targeted = (
        (relation_targeted_citation, claiming[0][1]),
        *((citation, provenance) for citation, provenance in pairs[1:]),
    )
    assert relation_provenance_ids(
        (claim.claim_assertion_id,), relation_targeted,
    ) == relation_provenance_ids(
        (claim.claim_assertion_id,),
        tuple(pairs[1:]),
    )
    assert relation_provenance_ids((claim.claim_assertion_id,), ()) == ()


def test_relation_pairing_requires_canonical_claim_payload_equality(fact_records):
    relation = _relation(fact_records)
    claim = _claim(fact_records)
    assert claim.claim_identity is not None
    identityless = claim.model_copy(update={"claim_identity": None})
    with pytest.raises(
        GraphObservationFeasibilityError,
        match="relation has no exactly paired supporting claim",
    ):
        project_relation_fields(relation, (identityless,), (_projection(fact_records),))
    mismatched = claim.model_copy(update={"claim_identity": claim.claim_identity.model_copy(
        update={"assertion_key_at_recording": claim.claim_identity.assertion_key_at_recording.model_copy(
            update={"slot": claim.claim_identity.assertion_key_at_recording.slot.model_copy(
                update={"subject_logical_entity_id": "other-subject-logical"},
            )},
        )},
    )})
    with pytest.raises(
        GraphObservationFeasibilityError,
        match="relation has no exactly paired supporting claim",
    ):
        project_relation_fields(relation, (mismatched,), (_projection(fact_records),))


def test_relation_interval_is_the_common_interval_of_exact_supporting_claims(fact_records):
    relation = _relation(fact_records)
    claim = _claim(fact_records)
    assert claim.valid_interval is not None
    overlapping = TimeInterval(
        start=claim.valid_interval.start.replace(day=15),
        end=claim.valid_interval.end,
    )
    second = _rebuild_claim(
        claim, claim_assertion_id="claim:overlap", interval=overlapping,
    )
    second_projection = ClaimProjection.create(
        operation_id=relation.operation_id,
        codec_fingerprint=_projection(fact_records).codec_fingerprint,
        claim_projection_id="projection:overlap",
        claim_assertion_id=second.claim_assertion_id,
        subject_entity_revision_id=relation.subject_entity_revision_id,
        subject_logical_entity_id=relation.subject_logical_entity_id,
        object_entity_revision_id=relation.object_entity_revision_id,
        object_logical_entity_id=relation.object_logical_entity_id,
    )
    fields = project_relation_fields(
        relation, (claim, second),
        (_projection(fact_records), second_projection),
    )
    assert fields.supporting_claim_assertion_ids == tuple(sorted((
        claim.claim_assertion_id, second.claim_assertion_id,
    )))
    assert fields.valid_interval == overlapping

    disjoint = TimeInterval(
        start=datetime(2026, 3, 1, tzinfo=UTC),
        end=datetime(2026, 4, 1, tzinfo=UTC),
    )
    far = _rebuild_claim(claim, claim_assertion_id="claim:disjoint", interval=disjoint)
    far_projection = ClaimProjection.create(
        operation_id=relation.operation_id,
        codec_fingerprint=_projection(fact_records).codec_fingerprint,
        claim_projection_id="projection:disjoint",
        claim_assertion_id=far.claim_assertion_id,
        subject_entity_revision_id=relation.subject_entity_revision_id,
        subject_logical_entity_id=relation.subject_logical_entity_id,
        object_entity_revision_id=relation.object_entity_revision_id,
        object_logical_entity_id=relation.object_logical_entity_id,
    )
    with pytest.raises(GraphObservationFeasibilityError, match="supporting claim interval disagreement"):
        project_relation_fields(
            relation, (claim, far),
            (_projection(fact_records), far_projection),
        )
    assert intersect_valid_intervals([None]) is None


def test_relation_rejects_unrelated_same_predicate_claims_and_missing_pairing(fact_records):
    relation = _relation(fact_records)
    claim = _claim(fact_records)
    projection = _projection(fact_records)
    unrelated = _rebuild_claim(claim, claim_assertion_id="claim:unrelated")
    unrelated_projection = ClaimProjection.create(
        operation_id=relation.operation_id,
        codec_fingerprint=projection.codec_fingerprint,
        claim_projection_id="projection:unrelated",
        claim_assertion_id=unrelated.claim_assertion_id,
        subject_entity_revision_id="other-subject-revision",
        subject_logical_entity_id="other-subject-logical",
        object_entity_revision_id=relation.object_entity_revision_id,
        object_logical_entity_id=relation.object_logical_entity_id,
    )
    projections = (projection, unrelated_projection)
    fields = project_relation_fields(relation, (claim, unrelated), projections)
    assert fields.supporting_claim_assertion_ids == (claim.claim_assertion_id,)
    assert unrelated_same_predicate_claims(relation, (claim, unrelated), projections) == (
        unrelated.claim_assertion_id,
    )
    with pytest.raises(
        GraphObservationFeasibilityError, match="relation has no exactly paired supporting claim",
    ):
        project_relation_fields(relation, (unrelated,), (unrelated_projection,))
    with pytest.raises(
        GraphObservationFeasibilityError, match="relation has no exactly paired supporting claim",
    ):
        project_relation_fields(relation, (claim,), (unrelated_projection,))


def _entity_pair():
    codec = next(
        entry.codec_fingerprint for entry in canonical_graph_codec_manifest().entries
        if entry.record_kind == "entity_revision"
    )
    evidence = (LineageEvidenceReference(
        source_id="src", start=0, end=5, evidence_digest="0" * 64,
    ),)
    first = EntityRevision.create(
        entity_revision_id="entity:versioned", logical_entity_id="logical:versioned",
        operation_id="op:1", codec_fingerprint=codec, source_evidence=evidence,
    )
    second = EntityRevision.create(
        entity_revision_id="entity:versioned", logical_entity_id="logical:versioned",
        operation_id="op:2", codec_fingerprint=codec, source_evidence=evidence,
        record_version=2,
    )
    return first, second


def _event(record, prior_record, *, timestamp, revision_before, revision_after):
    return build_semantic_memory_event(
        record=record,
        prior_record=prior_record,
        repository_id="repo",
        source_id="src",
        transaction_group_id="group",
        operation_fence_id="fence",
        writer_epoch=1,
        graph_revision_before=revision_before,
        graph_revision_after=revision_after,
        graph_delta_digest="1" * 64,
        timestamp=timestamp,
    )


def _prior(record, event, timestamp):
    return SemanticMaterializedMemoryRecord(
        record_kind=record.record_kind,
        record_id=record.entity_revision_id,
        record_version=record.record_version,
        record_digest=record.record_digest,
        record=record,
        source_event_id=event.source_event_id,
        source_event_digest=event.source_event_digest,
        source_id="src",
        transaction_group_id="group",
        system_valid_from=timestamp,
    )


def _event_pair(first_timestamp, second_timestamp):
    first, second = _entity_pair()
    first_event = _event(
        first, None, timestamp=first_timestamp, revision_before="r0", revision_after="r1",
    )
    second_event = _event(
        second, _prior(first, first_event, first_timestamp),
        timestamp=second_timestamp, revision_before="r1", revision_after="r2",
    )
    return first, second, first_event, second_event


def _positions(*sequences):
    return tuple(EventBatchLogPosition.create(repository_id="repo", sequence=item) for item in sequences)


def test_system_interval_orders_successors_by_event_sequence():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    later_time = datetime(2026, 1, 2, tzinfo=UTC)
    _, _, first_event, second_event = _event_pair(t0, later_time)
    derived = derive_system_interval(
        zip(
            (first_event, second_event),
            _positions(4, 7),
            strict=True,
        ),
        record_id="entity:versioned",
        record_digest=first_event.payload.record_digest,
    )
    assert derived.bounded
    assert derived.interval == TimeInterval(start=t0, end=later_time)
    assert derived.successor_event_id == second_event.event_id
    # A same-time successor is ordered by sequence but cannot become a
    # positive closed interval; its exact lineage is still retained.
    _, _, same_first, same_second = _event_pair(t0, t0)
    same_time = derive_system_interval(
        zip((same_first, same_second), _positions(4, 7), strict=True),
        record_id="entity:versioned",
        record_digest=same_first.payload.record_digest,
    )
    assert same_time.bounded is False
    assert same_time.interval == TimeInterval(start=t0, end=None)
    assert same_time.successor_event_id == same_second.event_id


def test_system_interval_requires_strict_event_ordering():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    _, _, first_event, second_event = _event_pair(t0, t0)
    with pytest.raises(GraphObservationFeasibilityError, match="ambiguous event ordering"):
        derive_system_interval(
            zip((first_event, second_event), _positions(3, 3), strict=True),
            record_id="entity:versioned",
            record_digest=first_event.payload.record_digest,
        )
    # A successor that the log orders before the event it advances denies.
    with pytest.raises(GraphObservationFeasibilityError, match="ambiguous event ordering"):
        derive_system_interval(
            zip((first_event, second_event), _positions(9, 2), strict=True),
            record_id="entity:versioned",
            record_digest=first_event.payload.record_digest,
        )


def test_system_interval_without_successor_is_unbounded_and_zero_events_denied():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    _first, _, first_event, _ = _event_pair(t0, t0)
    derived = derive_system_interval(
        ((first_event, EventBatchLogPosition.create(repository_id="repo", sequence=1)),),
        record_id="entity:versioned",
    )
    assert derived.bounded is False
    assert derived.interval == TimeInterval(start=t0, end=None)
    assert derived.successor_event_id is None
    assert derived.interval.start == first_event.timestamp
    with pytest.raises(GraphObservationFeasibilityError, match="no owning commit event"):
        derive_system_interval((), record_id="entity:versioned")
    with pytest.raises(GraphObservationFeasibilityError, match="no owning commit event"):
        derive_system_interval(
            ((first_event, EventBatchLogPosition.create(repository_id="repo", sequence=1)),),
            record_id="entity:absent",
        )


def test_system_interval_denies_ambiguous_owning_event_and_successor():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    t1 = datetime(2026, 1, 2, tzinfo=UTC)
    first, _second, first_event, second_event = _event_pair(t0, t1)
    third = EntityRevision.create(
        entity_revision_id="entity:versioned", logical_entity_id="logical:versioned",
        operation_id="op:3", codec_fingerprint=first.codec_fingerprint,
        source_evidence=first.source_evidence, record_version=2,
    )
    competing_event = _event(
        third, _prior(first, first_event, t0),
        timestamp=t1, revision_before="r1", revision_after="r3",
    )
    events = (first_event, second_event, competing_event)
    positions = _positions(1, 2, 3)
    with pytest.raises(GraphObservationFeasibilityError, match="ambiguous event successor"):
        derive_system_interval(
            zip(events, positions, strict=True),
            record_id="entity:versioned",
            record_digest=first.record_digest,
        )
    with pytest.raises(GraphObservationFeasibilityError, match="ambiguous owning commit event"):
        derive_system_interval(
            zip(events, positions, strict=True),
            record_id="entity:versioned",
        )


def test_unique_complete_retained_source_span_is_copied(captured_fact):
    _, _, group_request = captured_fact
    authority = group_request.ordered_operation_inputs[0].reduction.native_compilation.operation_input.planning_construction_authority
    span = authority.evidence_constructions[0].source_span
    reference = LineageEvidenceReference(
        source_id=span.source_id,
        start=span.segment_local_span.start,
        end=span.segment_local_span.end,
        evidence_digest="4" * 64,
    )
    other_source = span.model_copy(deep=True)
    other_source_copy = other_source.model_copy(update={"source_id": "other-source"})
    resolved = resolve_complete_source_span((other_source_copy, span), reference)
    assert resolved == span
    assert resolved.retained_text_artifact == span.retained_text_artifact
    assert resolved.text_mapping_proof == span.text_mapping_proof
    assert resolved.reference_digest == span.reference_digest


def test_missing_or_ambiguous_complete_source_span_denies(captured_fact):
    _, _, group_request = captured_fact
    authority = group_request.ordered_operation_inputs[0].reduction.native_compilation.operation_input.planning_construction_authority
    span = authority.evidence_constructions[0].source_span
    reference = LineageEvidenceReference(
        source_id=span.source_id,
        start=span.segment_local_span.start,
        end=span.segment_local_span.end,
        evidence_digest="4" * 64,
    )
    with pytest.raises(GraphObservationFeasibilityError, match="no complete retained source span"):
        resolve_complete_source_span((), reference)
    absent = LineageEvidenceReference(
        source_id="absent-source", start=0, end=1, evidence_digest="4" * 64,
    )
    with pytest.raises(GraphObservationFeasibilityError, match="no complete retained source span"):
        resolve_complete_source_span((span,), absent)
    duplicate = span.model_copy(update={"reference_digest": "5" * 64})
    with pytest.raises(GraphObservationFeasibilityError, match="ambiguous retained source span"):
        resolve_complete_source_span((span, duplicate), reference)


def test_lineage_reference_alone_cannot_manufacture_a_source_span(captured_fact):
    _, _, group_request = captured_fact
    authority = group_request.ordered_operation_inputs[0].reduction.native_compilation.operation_input.planning_construction_authority
    span = authority.evidence_constructions[0].source_span
    reference = LineageEvidenceReference(
        source_id=span.source_id,
        start=span.segment_local_span.start,
        end=span.segment_local_span.end,
        evidence_digest="4" * 64,
    )
    with pytest.raises(
        GraphObservationFeasibilityError,
        match="lineage evidence reference cannot manufacture a complete source span",
    ):
        lineage_reference_cannot_manufacture_span(reference)


def test_projection_observation_identity_round_trip_and_shape():
    identity = projection_observation_identity(
        "temporal", "repo:1", "1" * 64, "2" * 64,
    )
    assert len(identity) == 64
    assert all(character in "0123456789abcdef" for character in identity)
    assert verify_projection_observation_identity(
        "temporal", "repo:1", "1" * 64, "2" * 64, identity,
    )
    assert PROJECTION_IDENTITY_DOMAIN == (
        "memorii.semantic_ingestion.observation.ProjectionObservationIdentity.v1"
    )


@pytest.mark.parametrize("field", ["kind", "repository", "generation", "projection"])
def test_projection_observation_identity_binds_every_field(field):
    base = {
        "kind": "temporal", "repository": "repo:1",
        "generation": "1" * 64, "projection": "2" * 64,
    }
    identity = projection_observation_identity(
        base["kind"], base["repository"], base["generation"], base["projection"],
    )
    changed = dict(base)
    changed[field] = (
        {"kind": "trust", "repository": "repo:2", "generation": "3" * 64, "projection": "4" * 64}
    )[field]
    other = projection_observation_identity(
        changed["kind"], changed["repository"], changed["generation"], changed["projection"],
    )
    assert other != identity
    assert not verify_projection_observation_identity(
        changed["kind"], changed["repository"], changed["generation"], changed["projection"],
        identity,
    )


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"projection_kind": "structural"}, "not temporal or trust"),
        ({"repository_id": ""}, "repository is empty"),
        ({"generation_digest": "1" * 63}, "generation.*digest is not lowercase sha256"),
        ({"projection_digest": "A" * 64}, "projection.*digest is not lowercase sha256"),
    ],
)
def test_projection_identity_denies_nonconforming_preimage_fields(kwargs, match):
    arguments = {
        "projection_kind": "temporal", "repository_id": "repo:1",
        "generation_digest": "1" * 64, "projection_digest": "2" * 64,
    }
    arguments.update(kwargs)
    with pytest.raises(GraphObservationFeasibilityError, match=match):
        projection_observation_identity(**arguments)


def test_system_interval_ignores_cross_record_prior_digest_events():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    first, _, first_event, _ = _event_pair(t0, t0)
    other = EntityRevision.create(
        entity_revision_id="entity:other", logical_entity_id="logical:other",
        operation_id="op:9", codec_fingerprint=first.codec_fingerprint,
        source_evidence=first.source_evidence,
    )
    # The real event owner refuses to construct an update whose prior record
    # belongs to a different record lineage, so a cross-record successor
    # cannot exist through retained authority; the record_id filter in
    # derive_system_interval remains defense in depth.
    with pytest.raises(SemanticEventReplayError, match="exact predecessor"):
        _event(
            other, _prior(first, first_event, t0),
            timestamp=datetime(2026, 1, 2, tzinfo=UTC),
            revision_before="r1", revision_after="r9",
        )
