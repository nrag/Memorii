"""Focused proof for the native graph-observation projection on the real fact arm.

The production capture supplies one verified accepted fact operation with its
complete retained native record inventory.  Every test projects that arm (or a
rebuilt variant) through the registered observed roots and asserts the exact
promoted field semantics or the fail-closed denial.  No provider or public
endpoint is certified by these tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from memorii.core.memory_evolution.graph_observation_native_projection import (
    NativeGraphObservationProjectionError,
    _effect_authority,
    _intersect_valid_intervals,
    _supporting_claims,
    project_native_graph_observation_stream,
)
from memorii.core.memory_evolution.graph_observation_records import (
    ObservedEntityReference,
)
from memorii.core.memory_evolution.graph_planning import (
    AbsentPlanningPrecondition,
    PlanningCommitValues,
    canonical_planning_payload_from_record,
    materialize_canonical_planning_payload,
)
from memorii.core.memory_evolution.graph_records import (
    CanonicalEntityRevisionRef,
    CitationRecord,
    ClaimProjection,
    EntityRevision,
    ReferenceDispositionRecord,
    RelationRevision,
    SourceAuthority,
    TypeEvidence,
    canonical_graph_codec_manifest,
    graph_record_id,
)
from memorii.core.memory_evolution.semantic_state import LineageEvidenceReference
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.semantic_ingestion.contracts import (
    BootstrapNativeFactEffectV3,
    BootstrapNativePlanningRecordV3,
    ClaimAssertion,
    contract_digest,
)
from tests.fixtures.semantic_ingestion.observation_publication import (
    observation_publication,
)
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import (
    _capture_builtin_fact_planning,
)
from tests.unit.core.semantic_ingestion.test_semantic_provider_composition import (
    TEST_NOW,
)

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_FACT_ROOTS = (
    "ObservedEntityRevision", "ObservedClaimAssertion", "ObservedRelation",
    "ObservedCitationRecord", "ObservedProvenanceRecord",
)


@dataclass(frozen=True)
class _FactArm:
    compilation: object
    effect: BootstrapNativeFactEffectV3
    group_request: object
    commit_values: PlanningCommitValues
    records: tuple
    pairs: tuple
    lookup: dict
    boundary_ids: frozenset


@pytest.fixture(scope="module")
def captured_fact():
    patch = pytest.MonkeyPatch()
    try:
        return _capture_builtin_fact_planning(patch)
    finally:
        patch.undo()


def _materialize(effect, group_id: str, commit_values: PlanningCommitValues) -> tuple:
    return tuple(
        materialize_canonical_planning_payload(
            record.planning_payload, commit_values=commit_values,
            authorizing_transaction_group_id=group_id,
        )
        for record in effect.planning_records
    )


def _materialized_pairs(effect, commit_values: PlanningCommitValues) -> tuple:
    pairs = []
    for projection in effect.evidence_projections:
        citation = materialize_canonical_planning_payload(
            projection.citation_record.planning_payload, commit_values=commit_values,
            authorizing_transaction_group_id=commit_values.transaction_group_id,
        )
        provenance = materialize_canonical_planning_payload(
            projection.provenance_record.planning_payload, commit_values=commit_values,
            authorizing_transaction_group_id=commit_values.transaction_group_id,
        )
        assert isinstance(citation, CitationRecord)
        pairs.append((citation, provenance))
    return tuple(pairs)


@pytest.fixture(scope="module")
def arm(captured_fact) -> _FactArm:
    _, _, group_request = captured_fact
    compilation = group_request.ordered_operation_inputs[0].reduction.native_compilation
    effect = group_request.ordered_operation_inputs[0].reduction.effect_materialization.accepted_effect
    assert isinstance(effect, BootstrapNativeFactEffectV3)
    commit_values = PlanningCommitValues(
        transaction_group_id=group_request.transaction_group_id,
        graph_revision_before="native-projection-before",
        graph_revision_after="native-projection-after",
        committed_at=TEST_NOW,
    )
    records = _materialize(effect, group_request.transaction_group_id, commit_values)
    lookup = {
        record.entity_revision_id: ObservedEntityReference(
            entity_revision_id=record.entity_revision_id,
            logical_entity_id=record.logical_entity_id,
            reference_path="entity_revision_id",
        )
        for record in records if isinstance(record, EntityRevision)
    }
    claim = _claim(records)
    subject = _subject_entity(records)
    return _FactArm(
        compilation=compilation, effect=effect, group_request=group_request,
        commit_values=commit_values, records=records,
        pairs=_materialized_pairs(effect, commit_values), lookup=lookup,
        boundary_ids=frozenset({subject.entity_revision_id, claim.claim_assertion_id}),
    )


def _entity(records) -> EntityRevision:
    return next(record for record in records if isinstance(record, EntityRevision))


def _subject_entity(records) -> EntityRevision:
    relation = _relation(records)
    return next(
        record for record in records
        if isinstance(record, EntityRevision)
        and record.entity_revision_id == relation.subject_entity_revision_id
    )


def _claim(records) -> ClaimAssertion:
    return next(record for record in records if isinstance(record, ClaimAssertion))


def _relation(records) -> RelationRevision:
    return next(record for record in records if isinstance(record, RelationRevision))


def _projection(records) -> ClaimProjection:
    return next(record for record in records if isinstance(record, ClaimProjection))


def _project(arm: _FactArm, *, history, limits, **overrides):
    values = dict(
        compilation=arm.compilation,
        accepted_effect=arm.effect,
        retained_native_records=arm.records,
        evidence_pairs=arm.pairs,
        commit_values=arm.commit_values,
        authorizing_transaction_group_id=arm.group_request.transaction_group_id,
        native_entity_lookup=arm.lookup,
        boundary_ids=arm.boundary_ids,
        system_interval=TimeInterval(start=TEST_NOW),
        history=history,
        publication=history.publications[0],
        limits=limits,
    )
    values.update(overrides)
    return project_native_graph_observation_stream(**values)


def _codec(record_kind: str) -> str:
    return next(
        entry.codec_fingerprint for entry in canonical_graph_codec_manifest().entries
        if entry.record_kind == record_kind
    )


def _planning_record(arm: _FactArm, record) -> BootstrapNativePlanningRecordV3:
    return BootstrapNativePlanningRecordV3.create(
        operation_execution_id=arm.compilation.operation_execution_id,
        record_kind=record.record_kind,
        record_id=graph_record_id(record),
        precondition=AbsentPlanningPrecondition(),
        planning_payload=canonical_planning_payload_from_record(
            record, transaction_group_id=arm.group_request.transaction_group_id,
        ),
        source_member_digest=arm.compilation.operation_input.operation_subject.member_digest,
    )


def _effect_with_planning_records(
    effect: BootstrapNativeFactEffectV3, planning_records,
) -> BootstrapNativeFactEffectV3:
    values = effect.model_dump(mode="python", exclude={"schema_version", "effect_digest"})
    values["planning_records"] = tuple(
        record.model_dump(mode="python") for record in planning_records
    )
    return BootstrapNativeFactEffectV3.create(**values)


def _binding_projection(
    arm: _FactArm, relation: RelationRevision, claim_assertion_id: str,
) -> ClaimProjection:
    return ClaimProjection.create(
        operation_id=arm.compilation.operation_id,
        codec_fingerprint=_projection(arm.records).codec_fingerprint,
        claim_projection_id=f"projection:{claim_assertion_id}",
        claim_assertion_id=claim_assertion_id,
        subject_entity_revision_id=relation.subject_entity_revision_id,
        subject_logical_entity_id=relation.subject_logical_entity_id,
        object_entity_revision_id=relation.object_entity_revision_id,
        object_logical_entity_id=relation.object_logical_entity_id,
    )


def _type_evidence(
    entity: EntityRevision, asserted_type: str, *, span=None, logical_entity_id=None,
) -> TypeEvidence:
    reference = CanonicalEntityRevisionRef(
        entity_revision_id=entity.entity_revision_id,
        logical_entity_id=logical_entity_id or entity.logical_entity_id,
    )
    source_evidence = () if span is None else (LineageEvidenceReference(
        source_id=span.source_id, start=span.segment_local_span.start,
        end=span.segment_local_span.end, evidence_digest="4" * 64,
    ),)
    return TypeEvidence.create(
        operation_id=entity.operation_id, codec_fingerprint=_codec("type_evidence"),
        evidence_id=f"evidence:{asserted_type}:{span is not None}", entity_reference=reference,
        asserted_type=asserted_type, origin="verified_graph_type_assertion",
        source_evidence=source_evidence,
        authority=SourceAuthority(
            authority_class="projection-test", authenticated_provenance_class="projection-test",
            policy_revision="projection-test-1",
        ),
        recorded_at=TEST_NOW, proof_policy_fingerprint="3" * 64,
    )


def test_fact_operation_projects_exact_registered_observed_stream(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    system_interval = TimeInterval(start=TEST_NOW)
    stream = _project(arm, history=history, limits=limits)

    assert [item.record_kind for item in stream] == [
        "citation", "citation", "claim_assertion", "entity_revision", "entity_revision",
        "provenance", "provenance", "relation",
    ]
    for item in stream:
        assert item.record_digest == item.payload.record_digest
        assert _HEX64.fullmatch(item.record_digest)
        assert item.record_digest != "0" * 64
        if "system_interval" in type(item.payload).model_fields:
            assert item.payload.system_interval == system_interval
    assert stream == tuple(sorted(stream, key=lambda item: (item.record_kind, item.primary_key)))

    authority = arm.compilation.operation_input.planning_construction_authority
    claim = _claim(arm.records)
    relation = _relation(arm.records)
    subject = _subject_entity(arm.records)
    object_entity = next(
        record for record in arm.records
        if isinstance(record, EntityRevision)
        and record.entity_revision_id == relation.object_entity_revision_id
    )
    identity = claim.claim_identity
    assert identity is not None

    entities = {
        item.payload.entity_revision_id: item.payload
        for item in stream if item.record_kind == "entity_revision"
    }
    assert set(entities) == {subject.entity_revision_id, object_entity.entity_revision_id}
    for record in (subject, object_entity):
        payload = entities[record.entity_revision_id]
        assert payload.canonical_type is None
        assert payload.valid_interval is None
        assert payload.lifecycle_state == record.lifecycle == "active"
        assert payload.source_ids == (authority.source_id,)
        assert payload.operation_ids == (record.operation_id,)
        assert payload.boundary == (record.entity_revision_id in arm.boundary_ids)

    claim_payload = next(
        item.payload for item in stream if item.record_kind == "claim_assertion"
    )
    citing = tuple(
        pair for pair in arm.pairs
        if pair[0].cited_record_id == claim.claim_assertion_id
    )
    assert citing
    selected_evidence = next(
        candidate.authenticated_source_interval_evidence
        for candidate in claim.temporal_evidence.decision_closure.candidates
        if candidate.candidate_id in claim.temporal_evidence.decision_closure.selected_candidate_ids
    )
    fingerprints = {
        authority.predicate_registry_fingerprint,
        authority.predicate_state_rule.policy_fingerprint,
        authority.action_policy_fingerprint,
        *(item.temporal_policy_fingerprint for item in authority.temporal_constructions),
    }
    if authority.arbitration_policy_bundle is not None:
        fingerprints.add(authority.arbitration_policy_bundle.trust_policy.fingerprint)
        fingerprints.add(authority.arbitration_policy_bundle.temporal_policy.fingerprint)
    assert claim_payload.subject_assertion_ref.entity == arm.lookup[
        identity.subject_assertion_ref.entity_revision_id
    ]
    assert claim_payload.subject_assertion_ref.logical_entity_id_at_assertion == (
        identity.subject_assertion_ref.logical_entity_id_at_assertion
    )
    assert claim_payload.object_assertion_ref is not None
    assert claim_payload.object_assertion_ref.logical_entity_id_at_assertion == (
        identity.object_assertion_ref.logical_entity_id_at_assertion
    )
    assert claim_payload.assertion_key_at_recording == identity.assertion_key_at_recording
    assert claim_payload.predicate_id == identity.assertion_key_at_recording.slot.predicate_id
    assert claim_payload.literal_value is None
    assert claim_payload.polarity == arm.effect.fact.polarity == "positive"
    assert claim_payload.commitment == arm.effect.fact.commitment == "asserted"
    assert claim_payload.scope_identity == identity.assertion_key_at_recording.slot.scope_identity
    assert claim_payload.valid_interval == claim.valid_interval
    assert claim_payload.temporal_reference_evidence is None
    assert claim_payload.authenticated_source_interval_evidence == selected_evidence
    assert claim_payload.temporal_decision_binding == claim.temporal_decision_binding
    assert claim_payload.source_authority_class == (
        claim.source_authority_evidence.authority.authority_class
    )
    assert claim_payload.source_ids == (claim.source_authority_evidence.source_id,)
    assert claim_payload.operation_ids == (claim.operation_id,)
    assert claim_payload.citation_ids == tuple(sorted(pair[0].citation_id for pair in citing))
    assert claim_payload.provenance_ids == tuple(sorted(pair[1].provenance_id for pair in citing))
    assert claim_payload.policy_fingerprints == tuple(sorted(fingerprints))
    assert claim_payload.boundary is True

    relation_payload = next(item.payload for item in stream if item.record_kind == "relation")
    assert relation_payload.relation_id == relation.relation_revision_id
    assert relation_payload.predicate_id == relation.predicate_id
    assert relation_payload.subject == arm.lookup[relation.subject_entity_revision_id]
    assert relation_payload.object_kind == "entity"
    assert relation_payload.object_entity == arm.lookup[relation.object_entity_revision_id]
    assert relation_payload.literal_value is None
    assert relation_payload.supporting_claim_assertion_ids == (claim.claim_assertion_id,)
    assert relation_payload.lifecycle_state == "active"
    assert relation_payload.valid_interval == claim.valid_interval
    assert relation_payload.source_ids == (claim.source_authority_evidence.source_id,)
    assert relation_payload.provenance_ids == tuple(sorted(
        pair[1].provenance_id for pair in citing
    ))
    assert relation_payload.boundary is False

    citation_payloads = {
        item.payload.citation_id: item.payload
        for item in stream if item.record_kind == "citation"
    }
    assert set(citation_payloads) == {pair[0].citation_id for pair in arm.pairs}
    for citation_id, payload in citation_payloads.items():
        construction = next(
            item for item in authority.evidence_constructions
            if item.citation_id == citation_id
        )
        assert payload.cited_record_kind == "claim_assertion"
        assert payload.cited_record_id == claim.claim_assertion_id
        assert payload.source_span == construction.source_span
        assert payload.source_span.retained_text_artifact == construction.source_span.retained_text_artifact
        assert payload.source_span.text_mapping_proof == construction.source_span.text_mapping_proof
        assert payload.source_id == authority.source_id
        assert payload.source_digest == authority.source_digest
        assert payload.boundary is False

    provenance_payloads = {
        item.payload.provenance_id: item.payload
        for item in stream if item.record_kind == "provenance"
    }
    assert set(provenance_payloads) == {pair[1].provenance_id for pair in arm.pairs}
    for payload in provenance_payloads.values():
        assert payload.record_kind == "claim_assertion"
        assert payload.record_id == claim.claim_assertion_id
        assert payload.source_ids == (authority.source_id,)
        assert payload.operation_ids == (arm.compilation.operation_id,)
        assert {
            arm.compilation.compilation_digest, authority.authority_digest,
            arm.effect.effect_digest,
        } <= set(payload.proof_ancestry_ids)
        assert payload.policy_fingerprints == tuple(sorted(fingerprints))
        assert payload.boundary is False


def test_unique_eligible_retained_type_evidence_yields_canonical_type(
    tmp_path, monkeypatch, arm,
):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    entity = _entity(arm.records)
    retained = (*arm.records, _type_evidence(entity, "product"))
    stream = _project(arm, history=history, limits=limits, retained_native_records=retained)
    payload = next(
        item.payload for item in stream
        if item.record_kind == "entity_revision"
        and item.primary_key == entity.entity_revision_id
    )
    assert payload.canonical_type == "product"
    other_revision = EntityRevision.create(
        entity_revision_id="entity:other", logical_entity_id=entity.logical_entity_id,
        operation_id=entity.operation_id, codec_fingerprint=entity.codec_fingerprint,
        source_evidence=entity.source_evidence,
    )
    unrelated = _project(
        arm, history=history, limits=limits,
        retained_native_records=(
            *arm.records, _type_evidence(entity, "product"),
            _type_evidence(other_revision, "person"),
        ),
    )
    payload = next(
        item.payload for item in unrelated
        if item.record_kind == "entity_revision"
        and item.primary_key == entity.entity_revision_id
    )
    assert payload.canonical_type == "product"
    competing = (
        *arm.records, _type_evidence(entity, "product"), _type_evidence(entity, "person"),
    )
    with pytest.raises(NativeGraphObservationProjectionError, match="competing entity type evidence"):
        _project(arm, history=history, limits=limits, retained_native_records=competing)
    foreign_logical = (
        *arm.records, _type_evidence(entity, "product", logical_entity_id="logical:foreign"),
    )
    with pytest.raises(
        NativeGraphObservationProjectionError, match="foreign logical entity",
    ):
        _project(arm, history=history, limits=limits, retained_native_records=foreign_logical)


def test_retained_type_evidence_stream_copies_complete_source_spans(
    tmp_path, monkeypatch, arm,
):
    history, limits = observation_publication(
        tmp_path, monkeypatch, (*_FACT_ROOTS, "ObservedTypeEvidence"),
    )
    authority = arm.compilation.operation_input.planning_construction_authority
    span = authority.evidence_constructions[0].source_span
    entity = _entity(arm.records)
    evidence = TypeEvidence.create(
        operation_id=entity.operation_id, codec_fingerprint=_codec("type_evidence"),
        evidence_id="evidence:certified", entity_reference=CanonicalEntityRevisionRef(
            entity_revision_id=entity.entity_revision_id,
            logical_entity_id=entity.logical_entity_id,
        ),
        asserted_type="product", origin="certified_source_assertion",
        source_evidence=(LineageEvidenceReference(
            source_id=span.source_id, start=span.segment_local_span.start,
            end=span.segment_local_span.end, evidence_digest="4" * 64,
        ),),
        authority=SourceAuthority(
            authority_class="projection-test", authenticated_provenance_class="projection-test",
            policy_revision="projection-test-1",
        ),
        recorded_at=TEST_NOW, proof_policy_fingerprint="3" * 64,
        proof_ancestry_ids=("proof:ancestor",),
    )
    effect = _effect_with_planning_records(
        arm.effect, (*arm.effect.planning_records, _planning_record(arm, evidence)),
    )
    records = _materialize(effect, arm.group_request.transaction_group_id, arm.commit_values)
    stream = _project(
        arm, history=history, limits=limits, accepted_effect=effect,
        retained_native_records=records,
    )
    payload = next(item.payload for item in stream if item.record_kind == "type_evidence")
    assert payload.evidence_id == "evidence:certified"
    assert payload.entity == arm.lookup[entity.entity_revision_id]
    assert payload.asserted_type == "product"
    assert payload.origin == "certified_source_assertion"
    assert payload.source_evidence == (span,)
    assert payload.proof_ancestry_ids == ("proof:ancestor",)
    assert payload.proof_policy_fingerprint == "3" * 64
    assert payload.valid_interval is None
    assert payload.boundary is False
    entity_payload = next(
        item.payload for item in stream
        if item.record_kind == "entity_revision"
        and item.primary_key == entity.entity_revision_id
    )
    assert entity_payload.canonical_type == "product"


def test_incomplete_retained_source_span_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(
        tmp_path, monkeypatch, (*_FACT_ROOTS, "ObservedTypeEvidence"),
    )
    authority = arm.compilation.operation_input.planning_construction_authority
    span = authority.evidence_constructions[0].source_span
    entity = _entity(arm.records)
    evidence = TypeEvidence.create(
        operation_id=entity.operation_id, codec_fingerprint=_codec("type_evidence"),
        evidence_id="evidence:unresolvable", entity_reference=CanonicalEntityRevisionRef(
            entity_revision_id=entity.entity_revision_id,
            logical_entity_id=entity.logical_entity_id,
        ),
        asserted_type="product", origin="certified_source_assertion",
        source_evidence=(LineageEvidenceReference(
            source_id=span.source_id, start=0, end=999, evidence_digest="4" * 64,
        ),),
        authority=SourceAuthority(
            authority_class="projection-test", authenticated_provenance_class="projection-test",
            policy_revision="projection-test-1",
        ),
        recorded_at=TEST_NOW, proof_policy_fingerprint="3" * 64,
    )
    effect = _effect_with_planning_records(
        arm.effect, (*arm.effect.planning_records, _planning_record(arm, evidence)),
    )
    records = _materialize(effect, arm.group_request.transaction_group_id, arm.commit_values)
    with pytest.raises(
        NativeGraphObservationProjectionError, match="no complete retained source span",
    ):
        _project(
            arm, history=history, limits=limits, accepted_effect=effect,
            retained_native_records=records,
        )


def test_foreign_commit_group_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    with pytest.raises(
        NativeGraphObservationProjectionError, match="commit authority group is substituted",
    ):
        _project(
            arm, history=history, limits=limits,
            authorizing_transaction_group_id="f" * 64,
        )


def test_foreign_or_absent_operation_authority_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    stripped = arm.compilation.model_copy(update={
        "operation_input": arm.compilation.operation_input.model_copy(
            update={"planning_construction_authority": None},
        ),
    })
    with pytest.raises(
        NativeGraphObservationProjectionError, match="native operation authority is incomplete",
    ):
        _project(arm, history=history, limits=limits, compilation=stripped)
    unresolved = arm.compilation.model_copy(update={"terminal_status": "unresolved"})
    with pytest.raises(
        NativeGraphObservationProjectionError, match="native operation authority is incomplete",
    ):
        _project(arm, history=history, limits=limits, compilation=unresolved)
    authority = arm.compilation.operation_input.planning_construction_authority
    foreign = arm.compilation.model_copy(update={
        "operation_input": arm.compilation.operation_input.model_copy(
            update={"planning_construction_authority": authority.model_copy(
                update={"operation_id": "f" * 64},
            )},
        ),
    })
    with pytest.raises(
        NativeGraphObservationProjectionError, match="native operation authority is incomplete",
    ):
        _project(arm, history=history, limits=limits, compilation=foreign)
    foreign_member = arm.effect.model_copy(update={
        "fact": arm.effect.fact.model_copy(update={"polarity": "negative"}),
    })
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="accepted effect does not bind the compilation operation member",
    ):
        _project(arm, history=history, limits=limits, accepted_effect=foreign_member)


def test_substituted_retained_inventory_record_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    entity = _subject_entity(arm.records)
    substituted = EntityRevision.create(
        entity_revision_id=entity.entity_revision_id,
        logical_entity_id=entity.logical_entity_id,
        operation_id=entity.operation_id,
        codec_fingerprint=entity.codec_fingerprint,
        source_evidence=entity.source_evidence, lifecycle="retired",
    )
    retained = tuple(
        substituted if record is entity else record for record in arm.records
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="native record differs from canonical materialization",
    ):
        _project(arm, history=history, limits=limits, retained_native_records=retained)


def test_duplicate_retained_identity_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="retained native inventory has duplicate identities",
    ):
        _project(
            arm, history=history, limits=limits,
            retained_native_records=(*arm.records, arm.records[0]),
        )


def test_missing_native_entity_lookup_entry_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    entity = _subject_entity(arm.records)
    lookup = dict(arm.lookup)
    del lookup[entity.entity_revision_id]
    with pytest.raises(
        NativeGraphObservationProjectionError, match="native entity lookup is incomplete",
    ):
        _project(arm, history=history, limits=limits, native_entity_lookup=lookup)
    mismatched = dict(arm.lookup)
    mismatched[entity.entity_revision_id] = ObservedEntityReference(
        entity_revision_id=entity.entity_revision_id,
        logical_entity_id="logical:substituted", reference_path="entity_revision_id",
    )
    with pytest.raises(
        NativeGraphObservationProjectionError, match="native entity lookup is incomplete",
    ):
        _project(arm, history=history, limits=limits, native_entity_lookup=mismatched)


def test_claim_identity_payload_mismatch_excludes_relation_support(
    tmp_path, monkeypatch, arm,
):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    claim_planning = next(
        record for record in arm.effect.planning_records
        if record.record_kind == "claim_assertion"
    )
    values = claim_planning.model_dump(
        mode="python", exclude={"record_digest", "schema_version"},
    )
    payload = values["planning_payload"]["planning_record"]
    foreign = "logical:foreign-subject"
    payload["claim_identity"]["assertion_key_at_recording"]["slot"]["subject_logical_entity_id"] = foreign
    payload["claim_identity"]["subject_assertion_ref"]["logical_entity_id_at_assertion"] = foreign
    rebuilt = BootstrapNativePlanningRecordV3.create(**values)
    effect = _effect_with_planning_records(arm.effect, tuple(
        rebuilt if record is claim_planning else record
        for record in arm.effect.planning_records
    ))
    records = _materialize(effect, arm.group_request.transaction_group_id, arm.commit_values)
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="relation has no exactly paired supporting claim",
    ):
        _project(
            arm, history=history, limits=limits, accepted_effect=effect,
            retained_native_records=records,
        )


def test_relation_targeted_provenance_is_excluded(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    relation = _relation(arm.records)
    first_citation, first_provenance = arm.pairs[0]
    relation_targeted = (
        (first_citation.model_copy(update={
            "cited_record_id": relation.relation_revision_id,
        }), first_provenance),
        *arm.pairs[1:],
    )
    stream = _project(arm, history=history, limits=limits, evidence_pairs=relation_targeted)
    claim_payload = next(item.payload for item in stream if item.record_kind == "claim_assertion")
    assert claim_payload.citation_ids == tuple(sorted(
        pair[0].citation_id for pair in arm.pairs[1:]
    ))
    assert claim_payload.provenance_ids == tuple(sorted(
        pair[1].provenance_id for pair in arm.pairs[1:]
    ))
    relation_payload = next(item.payload for item in stream if item.record_kind == "relation")
    assert relation_payload.provenance_ids == tuple(sorted(
        pair[1].provenance_id for pair in arm.pairs[1:]
    ))
    assert first_provenance.provenance_id not in relation_payload.provenance_ids


def test_supporting_interval_disagreement_denies(arm):
    """The fact arm structurally retains one claim; the common-interval rule is
    proven on the production join helpers with two exact supporting claims."""
    relation = _relation(arm.records)
    claim = _claim(arm.records)
    projection = _projection(arm.records)
    assert claim.valid_interval is not None
    overlapping = TimeInterval(
        start=claim.valid_interval.start.replace(day=15), end=claim.valid_interval.end,
    )
    second = _rebuild_claim(claim, claim_assertion_id="claim:overlap", interval=overlapping)
    second_projection = _binding_projection(arm, relation, second.claim_assertion_id)
    supporting = _supporting_claims(
        relation, (claim, second), (projection, second_projection),
    )
    assert tuple(item.claim_assertion_id for item in supporting) == (
        claim.claim_assertion_id, second.claim_assertion_id,
    )
    assert _intersect_valid_intervals(
        [item.valid_interval for item in supporting]
    ) == overlapping
    assert _intersect_valid_intervals([claim.valid_interval, None]) == claim.valid_interval
    assert _intersect_valid_intervals([None]) is None
    disjoint = TimeInterval(
        start=datetime(2026, 3, 1, tzinfo=UTC), end=datetime(2026, 4, 1, tzinfo=UTC),
    )
    far = _rebuild_claim(claim, claim_assertion_id="claim:disjoint", interval=disjoint)
    far_supporting = _supporting_claims(
        relation, (claim, far), (projection, _binding_projection(arm, relation, far.claim_assertion_id)),
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="supporting claim interval disagreement",
    ):
        _intersect_valid_intervals([item.valid_interval for item in far_supporting])
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="relation has no exactly paired supporting claim",
    ):
        _intersect_valid_intervals([])


def test_identityless_claim_is_never_relation_support(arm):
    relation = _relation(arm.records)
    claim = _claim(arm.records)
    projection = _projection(arm.records)
    assert _supporting_claims(relation, (claim,), (projection,)) == (claim,)
    identityless = claim.model_copy(update={"claim_identity": None})
    assert _supporting_claims(relation, (identityless,), (projection,)) == ()


def test_unsupported_retained_record_kind_and_arm_deny(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    entity = _subject_entity(arm.records)
    disposition = ReferenceDispositionRecord.create(
        operation_id=arm.compilation.operation_id,
        codec_fingerprint=_codec("reference_disposition"),
        reference_disposition_id="reference-disposition:unsupported",
        target_record_kind="entity_revision", target_record_id=entity.entity_revision_id,
        target_reference_path="entity_revision_id",
        predecessor_entity_revision_id=entity.entity_revision_id,
        predecessor_logical_entity_id=entity.logical_entity_id,
        disposition="unresolved", basis="insufficient_evidence",
    )
    effect = _effect_with_planning_records(
        arm.effect, (*arm.effect.planning_records, _planning_record(arm, disposition)),
    )
    records = _materialize(effect, arm.group_request.transaction_group_id, arm.commit_values)
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="retained native record kind has no exact observed projection recipe: "
        "reference_disposition",
    ):
        _project(
            arm, history=history, limits=limits, accepted_effect=effect,
            retained_native_records=records,
        )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="accepted operation arm has no exact observed projection recipe",
    ):
        _effect_authority(object(), compilation=arm.compilation)


def _rebuild_claim(claim: ClaimAssertion, *, claim_assertion_id=None, interval=None):
    """Retained-authority claim rebuild mirroring the approved feasibility."""
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
