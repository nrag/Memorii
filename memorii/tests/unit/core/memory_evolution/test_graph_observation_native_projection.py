"""Focused proof for the native graph-observation projection on the real fact arm.

The production capture supplies one verified accepted fact operation with its
complete retained native record inventory.  Every test projects that arm (or a
rebuilt variant) through the registered observed roots and asserts the exact
promoted field semantics or the fail-closed denial.  The sibling-arm envelope
tests build correction/retraction/action/identity envelopes from the same real
fact capture through the real contract constructors (the validated feasibility
builders), because the current production planner never commits non-fact
cohorts -- no real-store sibling-arm cohort exists yet and none is claimed.
No provider or public endpoint is certified by these tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from memorii.core.memory_evolution.graph_observation_native_projection import (
    NativeGraphObservationProjectionError,
    _effect_authority,
    _intersect_valid_intervals,
    _supporting_claims,
    project_boundary_entity_revision,
    project_native_graph_observation_stream,
)
from memorii.core.memory_evolution.graph_observation_records import (
    ObservedEntityReference,
)
from memorii.core.memory_evolution.graph_planning import (
    AbsentPlanningPrecondition,
    GraphPlanningState,
    NonPublishingIdentityPlanningResultV3,
    PlanningCommitValues,
    build_frozen_identity_graph_planning_artifact_from_state,
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
    TrustedAcceptedIdentityOperationDecision,
    TypeEvidence,
    VerifiedIdentityDecisionAuthority,
    canonical_graph_codec_manifest,
    graph_record_id,
)
from memorii.core.memory_evolution.identity_lineage import identity_lineage_genesis_digest
from memorii.core.memory_evolution.reference_integrity import bootstrap_reference_integrity
from memorii.core.memory_evolution.semantic_state import (
    AcceptedIdentityOperation,
    CompiledIdentityLineageTransition,
    LineageEntityIdentity,
    LineageEvidenceReference,
    LineageReferenceDisposition,
    LineageReverseReference,
)
from memorii.core.memory_evolution.time_contracts import TimeInterval
from memorii.core.memory_evolution.transaction_coordinator import (
    SemanticIngestionTransactionCoordinator,
)
from memorii.core.semantic_ingestion.contracts import (
    AcceptedActionTransitionReference,
    ActionRevision,
    ActionTransitionApplicabilityKey,
    BootstrapCanonicalIdentityBindingAllocationAuthorityV3,
    BootstrapCanonicalIdentityBindingAllocationReloadV3,
    BootstrapGraphTargetReferenceV3,
    BootstrapNativeActionStateEffectV3,
    BootstrapNativeCorrectionEffectV3,
    BootstrapNativeFactEffectV3,
    BootstrapNativeIdentityConstructionAuthorityV3,
    BootstrapNativeIdentityEffectV3,
    BootstrapNativeIdentityMaterializationV3,
    BootstrapNativePlanningRecordV3,
    BootstrapNativeRetractionEffectV3,
    BootstrapNativeTargetBindingV3,
    BootstrapNativeTemporalConstructionV3,
    BootstrapProposalActionRoleBindingV3,
    BootstrapProposalActionRoleParticipantV3,
    BootstrapProposalActionStateV3,
    BootstrapProposalCorrectionV3,
    BootstrapProposalIdentityOperationV3,
    BootstrapProposalRetractionV3,
    BootstrapSnapshotTargetAuthorityV3,
    CertifiedTextEffectiveTime,
    ClaimAssertion,
    IdentityLineageRecord,
    SystemRecordedEffectiveTime,
    TemporalTransitionRecord,
    contract_digest,
)
from memorii.core.semantic_ingestion.event_replay import SemanticReplayState
from tests.fixtures.semantic_ingestion.observation_publication import (
    observation_publication,
)
from tests.fixtures.semantic_ingestion.semantic_terminal_fixture import accepted_terminal
from tests.unit.core.semantic_ingestion.test_bootstrap_graph_observation_retention import (
    _capture_builtin_fact_planning,
)
from tests.unit.core.semantic_ingestion.test_identity_lineage_prerequisites import (
    _artifact as _identity_artifact,
)
from tests.unit.core.semantic_ingestion.test_identity_lineage_prerequisites import (
    _Reader,
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
        record.entity_revision_id: record.logical_entity_id
        for record in records if isinstance(record, EntityRevision)
    }
    return _FactArm(
        compilation=compilation, effect=effect, group_request=group_request,
        commit_values=commit_values, records=records,
        pairs=_materialized_pairs(effect, commit_values), lookup=lookup,
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


def _commit_event_intervals(records) -> dict[tuple[str, str], TimeInterval]:
    """Event-derived intervals as the materialization provider joins them.

    Every captured record version is owned by one commit event at the frozen
    writer clock TEST_NOW and has no successor, matching the real backend's
    event batches.
    """
    return {
        (record.record_kind, graph_record_id(record)): TimeInterval(start=TEST_NOW)
        for record in records
    }


def _project(arm: _FactArm, *, history, limits, **overrides):
    values = dict(
        compilation=arm.compilation,
        accepted_effect=arm.effect,
        retained_native_records=arm.records,
        evidence_pairs=arm.pairs,
        commit_values=arm.commit_values,
        authorizing_transaction_group_id=arm.group_request.transaction_group_id,
        native_entity_lookup=arm.lookup,
        history=history,
        publication=history.publications[0],
        limits=limits,
    )
    values.update(overrides)
    values.setdefault(
        "system_intervals",
        _commit_event_intervals(values["retained_native_records"]),
    )
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


def _expected_reference(arm: _FactArm, entity_revision_id: str, path: str):
    return ObservedEntityReference(
        entity_revision_id=entity_revision_id,
        logical_entity_id=arm.lookup[entity_revision_id],
        reference_path=path,
    )


def test_fact_operation_projects_exact_registered_observed_stream(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
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
            # System intervals are the commit-event time (TEST_NOW), never a
            # snapshot or request time.
            assert item.payload.system_interval == TimeInterval(start=TEST_NOW)
    assert stream == tuple(sorted(stream, key=lambda item: (item.record_kind, item.primary_key)))
    # Re-projecting the same retained authority is deterministic.
    assert _project(arm, history=history, limits=limits) == stream

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
        assert payload.boundary is False

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
    assert claim_payload.subject_assertion_ref.entity == _expected_reference(
        arm, identity.subject_assertion_ref.entity_revision_id,
        "/claim_identity/subject_assertion_ref/entity_revision_id",
    )
    assert claim_payload.subject_assertion_ref.logical_entity_id_at_assertion == (
        identity.subject_assertion_ref.logical_entity_id_at_assertion
    )
    assert claim_payload.object_assertion_ref is not None
    assert claim_payload.object_assertion_ref.entity == _expected_reference(
        arm, identity.object_assertion_ref.entity_revision_id,
        "/claim_identity/object_assertion_ref/entity_revision_id",
    )
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
    assert claim_payload.boundary is False

    relation_payload = next(item.payload for item in stream if item.record_kind == "relation")
    assert relation_payload.relation_id == relation.relation_revision_id
    assert relation_payload.predicate_id == relation.predicate_id
    assert relation_payload.subject == _expected_reference(
        arm, relation.subject_entity_revision_id, "subject_entity_revision_id",
    )
    assert relation_payload.object_kind == "entity"
    assert relation_payload.object_entity == _expected_reference(
        arm, relation.object_entity_revision_id, "object_entity_revision_id",
    )
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
    object_entity = next(
        record for record in arm.records
        if isinstance(record, EntityRevision)
        and record.entity_revision_id != entity.entity_revision_id
    )
    sibling = _project(
        arm, history=history, limits=limits,
        retained_native_records=(
            *arm.records, _type_evidence(entity, "product"),
            _type_evidence(object_entity, "person"),
        ),
    )
    payload = next(
        item.payload for item in sibling
        if item.record_kind == "entity_revision"
        and item.primary_key == entity.entity_revision_id
    )
    # Evidence bound to another entity revision of the same closed inventory
    # joins the cohort without disturbing this entity's canonical type.
    assert payload.canonical_type == "product"
    foreign_revision = EntityRevision.create(
        entity_revision_id="entity:foreign", logical_entity_id=entity.logical_entity_id,
        operation_id=entity.operation_id, codec_fingerprint=entity.codec_fingerprint,
        source_evidence=entity.source_evidence,
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="retained native inventory is not closed by the operation's planning records",
    ):
        _project(
            arm, history=history, limits=limits,
            retained_native_records=(
                *arm.records, _type_evidence(entity, "product"),
                _type_evidence(foreign_revision, "person"),
            ),
        )
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
    assert payload.entity == _expected_reference(
        arm, entity.entity_revision_id, "entity_reference.entity_revision_id",
    )
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


def test_unmatched_retained_inventory_record_denies(tmp_path, monkeypatch, arm):
    """The planning records must close the retained inventory: a retained
    record consumed by no planning record and holding no recognized join
    helper role denies."""
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    entity = _entity(arm.records)
    unmatched = EntityRevision.create(
        entity_revision_id="entity:unmatched", logical_entity_id=entity.logical_entity_id,
        operation_id=entity.operation_id, codec_fingerprint=entity.codec_fingerprint,
        source_evidence=entity.source_evidence,
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="retained native inventory is not closed by the operation's planning records: "
        "entity_revision entity:unmatched",
    ):
        _project(
            arm, history=history, limits=limits,
            retained_native_records=(*arm.records, unmatched),
        )
    # Type evidence bound to a foreign revision is not a recognized join helper.
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="retained native inventory is not closed by the operation's planning records: "
        "type_evidence evidence:person:False",
    ):
        _project(
            arm, history=history, limits=limits,
            retained_native_records=(*arm.records, _type_evidence(unmatched, "person")),
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
    mismatched[entity.entity_revision_id] = "logical:substituted"
    with pytest.raises(
        NativeGraphObservationProjectionError, match="native entity lookup is incomplete",
    ):
        _project(arm, history=history, limits=limits, native_entity_lookup=mismatched)


def test_missing_commit_event_system_interval_denies(tmp_path, monkeypatch, arm):
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    intervals = _commit_event_intervals(arm.records)
    entity = _subject_entity(arm.records)
    del intervals[("entity_revision", entity.entity_revision_id)]
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="observed entity_revision has no commit-event-derived system interval",
    ):
        _project(arm, history=history, limits=limits, system_intervals=intervals)
    claim = _claim(arm.records)
    intervals = _commit_event_intervals(arm.records)
    del intervals[("claim_assertion", claim.claim_assertion_id)]
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="observed claim_assertion has no commit-event-derived system interval",
    ):
        _project(arm, history=history, limits=limits, system_intervals=intervals)


def test_boundary_entity_revision_emits_boundary_record(tmp_path, monkeypatch, arm):
    """A referenced-but-unchanged entity revision is emitted as a boundary
    record whose fields derive only from its own retained authority."""
    history, limits = observation_publication(tmp_path, monkeypatch, _FACT_ROOTS)
    entity = _subject_entity(arm.records)
    interval = TimeInterval(start=TEST_NOW.replace(day=15))
    record = project_boundary_entity_revision(
        entity,
        retained_type_evidence=(),
        system_interval=interval,
        history=history, publication=history.publications[0], limits=limits,
    )
    payload = record.payload
    assert record.record_kind == "entity_revision"
    assert record.primary_key == entity.entity_revision_id
    assert record.record_digest == payload.record_digest
    assert _HEX64.fullmatch(payload.record_digest)
    assert payload.entity_revision_id == entity.entity_revision_id
    assert payload.logical_entity_id == entity.logical_entity_id
    assert payload.canonical_type is None
    assert payload.lifecycle_state == entity.lifecycle
    assert payload.valid_interval is None
    assert payload.system_interval == interval
    assert payload.source_ids == tuple(sorted({
        item.source_id for item in entity.source_evidence
    }))
    assert payload.operation_ids == (entity.operation_id,)
    assert payload.boundary is True
    # Retained type evidence bound to the exact revision supplies the type.
    evidence = _type_evidence(entity, "product")
    typed = project_boundary_entity_revision(
        entity,
        retained_type_evidence=(evidence,),
        system_interval=interval,
        history=history, publication=history.publications[0], limits=limits,
    )
    assert typed.payload.canonical_type == "product"
    assert typed.payload.record_digest != payload.record_digest
    # Competing retained type evidence on the exact revision denies.
    with pytest.raises(
        NativeGraphObservationProjectionError, match="competing entity type evidence",
    ):
        project_boundary_entity_revision(
            entity,
            retained_type_evidence=(evidence, _type_evidence(entity, "person")),
            system_interval=interval,
            history=history, publication=history.publications[0], limits=limits,
        )


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
    # ``reference_disposition`` is now a supported kind owned by identity arms;
    # a fact arm retaining one still denies through the exact arm mismatch.
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="reference disposition is retained by an operation arm that does not own it",
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


# --- Sibling-arm envelope proofs -------------------------------------------------
#
# The current production planner never commits non-fact cohorts, so no
# real-store sibling-arm cohort exists.  These envelope tests build each arm
# from the real fact capture through the real contract constructors (the
# validated feasibility builders) and project them through the registered
# roots; they prove the exact field recipes and typed refusals, never a
# provider run or a committed cohort.

_SIBLING_ROOTS = _FACT_ROOTS + (
    "ObservedTemporalTransition", "ObservedActionRevision",
    "ObservedIdentityTransition", "ObservedReferenceDisposition",
)


def _authority_values(arm: _FactArm) -> dict:
    authority = arm.compilation.operation_input.planning_construction_authority
    assert authority is not None
    return {
        name: getattr(authority, name)
        for name in type(authority).model_fields
        if name not in {"schema_version", "authority_digest"}
    }


def _rebuild_authority(arm: _FactArm, **changes):
    """Rebuild the captured authority through its real constructor."""
    values = _authority_values(arm) | changes
    authority = arm.compilation.operation_input.planning_construction_authority
    assert authority is not None
    return type(authority).create(**values)


def _compilation_with_authority(arm: _FactArm, authority, *, operation_member=None):
    """Rebind the captured compilation's authority (and optionally member).

    ``model_copy`` is used only to assemble the already-verified captured
    compilation around the rebuilt authority; every projection-side join
    (operation identity, member binding, terminal status) is re-checked by
    the projection owner itself.
    """
    operation_input = arm.compilation.operation_input.model_copy(update={
        "planning_construction_authority": authority,
        **({} if operation_member is None else {"operation_member": operation_member}),
    })
    return arm.compilation.model_copy(update={
        "operation_input": operation_input,
        **({} if operation_member is None else {"operation_member": operation_member}),
    })


def _rebased_transition(arm: _FactArm, kind: str, *, transition_kind=None):
    """Rebind the fixture's real transition carrier to this native operation.

    The generic terminal fixture derives its own operation identity; the typed
    transition authority is rebound through its owners exactly as the closed
    feasibility did, recomputing every digest.
    """
    carrier = next(
        item for item in accepted_terminal(
            operation_id="op:sibling-transition", operation_kind=kind,
        ).accepted_carriers if isinstance(item, TemporalTransitionRecord)
    )
    original = carrier.temporal_decision_binding
    attachment = type(original.temporal_attachment).create(**{
        **{name: getattr(original.temporal_attachment, name)
           for name in type(original.temporal_attachment).model_fields
           if name != "binding_digest"},
        "operation_id": arm.compilation.operation_id,
    })
    binding = type(original).create(**{
        **{name: getattr(original, name)
           for name in type(original).model_fields if name != "binding_digest"},
        "operation_id": arm.compilation.operation_id,
        "temporal_attachment": attachment,
    })
    body = carrier.model_dump(mode="python", exclude={"record_digest"}) | {
        "operation_id": arm.compilation.operation_id,
        "temporal_decision_binding": binding.model_dump(mode="python"),
    }
    if transition_kind is not None:
        body["transition_kind"] = transition_kind
    carrier = TemporalTransitionRecord.model_validate({
        **body,
        "record_digest": contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1", body,
        ),
    })
    planning = BootstrapNativePlanningRecordV3.create(
        operation_execution_id=arm.compilation.operation_execution_id,
        record_kind="temporal_transition", record_id=carrier.transition_id,
        precondition=AbsentPlanningPrecondition(),
        planning_payload=canonical_planning_payload_from_record(
            carrier, transaction_group_id=arm.group_request.transaction_group_id,
        ),
        source_member_digest=arm.effect.fact.fact_digest,
    )
    return carrier, planning, binding


def _transition_construction(binding, evidence, *, coordinate):
    closure = evidence.decision_closure
    return BootstrapNativeTemporalConstructionV3.create(
        temporal_role="transition",
        temporal_consensus_digest=binding.temporal_attachment.stable_attachment_consensus_digest,
        effective_time=coordinate,
        accepted_temporal_evidence=evidence,
        temporal_decision_binding=binding,
        temporal_policy_fingerprint=closure.temporal_policy_fingerprint,
    )


def _certified_coordinate(arm: _FactArm, evidence):
    closure = evidence.decision_closure
    assert evidence.valid_interval is not None
    authority = arm.compilation.operation_input.planning_construction_authority
    assert authority is not None
    return CertifiedTextEffectiveTime(
        kind="certified_text_time",
        effective_at=evidence.valid_interval.start,
        evidence_spans=(authority.evidence_constructions[0].source_span,),
        temporal_policy_fingerprint=closure.temporal_policy_fingerprint,
        temporal_policy_snapshot_digest=closure.temporal_policy_snapshot_digest,
    )


def _claim_target_binding(arm: _FactArm, claim: ClaimAssertion, *, role: str):
    target = BootstrapGraphTargetReferenceV3.create(
        record_kind="claim_assertion", record_id=claim.claim_assertion_id,
        record_digest=claim.record_digest,
    )
    return BootstrapNativeTargetBindingV3.create(
        role=role, source_coordinate_digest="a" * 64,
        authority=BootstrapSnapshotTargetAuthorityV3.create(
            kind="snapshot", target=target,
            sealed_snapshot_digest="0" * 64, effective_read_set_digest="0" * 64,
            snapshot_record_digest=target.record_digest,
        ),
    )


def _recreate(value, **changes):
    return type(value).create(**{
        **{name: getattr(value, name) for name in type(value).model_fields
           if name not in {"schema_version", value._digest_field}},
        **changes,
    })


def _citation_citing(arm: _FactArm, record_id: str):
    """Rebind the captured citation/provenance pair to one exact new target."""
    original = arm.effect.evidence_projections[0]
    payload = dict(original.citation_record.planning_payload.planning_record)
    payload["cited_record_id"] = record_id
    citation = _recreate(
        original.citation_record,
        planning_payload=type(original.citation_record.planning_payload)(
            planning_record=payload,
        ),
    )
    return _recreate(original, citation_record=citation)


def test_correction_arm_projects_replacement_and_transition_envelope(
    tmp_path, monkeypatch, arm,
):
    history, limits = observation_publication(tmp_path, monkeypatch, _SIBLING_ROOTS)
    claim = _claim(arm.records)
    identity = claim.claim_identity
    assert identity is not None
    carrier, transition, binding = _rebased_transition(arm, "correction")
    coordinate = _certified_coordinate(arm, carrier.temporal_evidence)
    construction = _transition_construction(
        binding, carrier.temporal_evidence, coordinate=coordinate,
    )
    # The captured arm retains an arbitration bundle whose policy fingerprints
    # belong to the fact capture; the rebased transition construction carries
    # the fixture's own policies, so the rebuilt authority drops the bundle
    # (a permitted absent optional) exactly like the closed feasibility.
    authority = _rebuild_authority(
        arm, arbitration_policy_bundle=None,
        temporal_constructions=(
            *arm.compilation.operation_input.planning_construction_authority.temporal_constructions,
            construction,
        ),
    )
    compilation = _compilation_with_authority(
        arm, authority, operation_member=BootstrapProposalCorrectionV3.create(
            corrected_fact=arm.effect.fact, replacement_fact=arm.effect.fact,
            assertion=arm.effect.fact.assertion,
            correction_anchor=arm.effect.fact.predicate_anchor,
        ),
    )
    replacement = _recreate(
        arm.effect,
        planning_records=(*arm.effect.planning_records, transition),
    )
    correction = BootstrapNativeCorrectionEffectV3.create(
        kind="correction",
        correction=compilation.operation_input.operation_member,
        corrected_targets=(
            _claim_target_binding(arm, claim, role="corrected_target"),
        ),
        replacement_effect=replacement, transition_records=(transition,),
    )
    records = _materialize(
        replacement, arm.group_request.transaction_group_id, arm.commit_values,
    )
    intervals = _commit_event_intervals(records)
    stream = _project(
        arm, history=history, limits=limits, compilation=compilation,
        accepted_effect=correction, retained_native_records=records,
        system_intervals=intervals,
    )
    assert [item.record_kind for item in stream] == [
        "citation", "citation", "claim_assertion", "entity_revision",
        "entity_revision", "provenance", "provenance", "relation",
        "temporal_transition",
    ]
    transition_payload = stream[-1].payload
    assert stream[-1].primary_key == carrier.transition_id
    assert transition_payload.transition_id == carrier.transition_id
    assert transition_payload.operation_id == arm.compilation.operation_id
    assert transition_payload.claim_slot_key == identity.assertion_key_at_recording.slot
    assert transition_payload.compared_claim_ids == (claim.claim_assertion_id,)
    assert transition_payload.previous_projection_claim_ids == (claim.claim_assertion_id,)
    assert transition_payload.next_projection_claim_ids == (claim.claim_assertion_id,)
    assert transition_payload.transition_kind == "correction"
    assert transition_payload.effective_time.kind == "certified_text_time"
    assert transition_payload.effective_time.effective_at == coordinate.effective_at
    assert transition_payload.effective_time.evidence_spans == coordinate.evidence_spans
    assert transition_payload.effective_time.temporal_policy_fingerprint == (
        coordinate.temporal_policy_fingerprint
    )
    assert transition_payload.transition_temporal_evidence == carrier.temporal_evidence
    assert transition_payload.transition_temporal_decision_binding == binding
    assert transition_payload.system_interval == TimeInterval(start=TEST_NOW)
    assert transition_payload.source_ids == (authority.source_id,)
    assert transition_payload.provenance_ids == ()
    assert transition_payload.boundary is False
    assert _HEX64.fullmatch(stream[-1].record_digest)
    assert stream[-1].record_digest == transition_payload.record_digest

    # A missing or ambiguous transition temporal construction denies.
    correction_member = compilation.operation_input.operation_member
    stripped = _rebuild_authority(arm, arbitration_policy_bundle=None)
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="transition lacks its unique retained transition temporal authority",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(
                arm, stripped, operation_member=correction_member,
            ),
            accepted_effect=correction, retained_native_records=records,
            system_intervals=intervals,
        )
    duplicated = _rebuild_authority(
        arm, arbitration_policy_bundle=None,
        temporal_constructions=(
            *_authority_values(arm)["temporal_constructions"], construction, construction,
        ),
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="transition lacks its unique retained transition temporal authority",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(
                arm, duplicated, operation_member=correction_member,
            ),
            accepted_effect=correction, retained_native_records=records,
            system_intervals=intervals,
        )
    # The coordinate discriminator must match the evidence the binding
    # carries: an interval-evidenced transition cannot be system-recorded-only.
    ambiguous = _rebuild_authority(
        arm, arbitration_policy_bundle=None,
        temporal_constructions=(
            *_authority_values(arm)["temporal_constructions"],
            _transition_construction(
                binding, carrier.temporal_evidence,
                coordinate=SystemRecordedEffectiveTime(
                    kind="system_recorded_only",
                    temporal_policy_fingerprint=(
                        carrier.temporal_evidence.decision_closure.temporal_policy_fingerprint
                    ),
                    temporal_policy_snapshot_digest=(
                        carrier.temporal_evidence.decision_closure.temporal_policy_snapshot_digest
                    ),
                ),
            ),
        ),
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="transition effective-time evidence is ambiguous",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(
                arm, ambiguous, operation_member=correction_member,
            ),
            accepted_effect=correction, retained_native_records=records,
            system_intervals=intervals,
        )
    # A transition version without its commit-event-derived interval denies.
    missing_interval = dict(intervals)
    del missing_interval[("temporal_transition", carrier.transition_id)]
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="observed temporal_transition has no commit-event-derived system interval",
    ):
        _project(
            arm, history=history, limits=limits, compilation=compilation,
            accepted_effect=correction, retained_native_records=records,
            system_intervals=missing_interval,
        )


def test_retraction_arm_transition_envelope_denies_without_claim_slot_authority(
    tmp_path, monkeypatch, arm,
):
    """The retraction envelope retains no claim identity for its transition.

    The retracted target is only a claim reference and the retraction proposal
    carries mention digests, so no retained carrier supplies the observed
    transition's claim slot key: the projection is a typed refusal, never a
    guessed slot.  Every other retraction join (arm ownership, kind,
    transition temporal authority) must still succeed first.
    """
    history, limits = observation_publication(tmp_path, monkeypatch, _SIBLING_ROOTS)
    claim = _claim(arm.records)
    carrier, transition, binding = _rebased_transition(arm, "retraction")
    coordinate = _certified_coordinate(arm, carrier.temporal_evidence)
    authority = _rebuild_authority(
        arm, arbitration_policy_bundle=None,
        temporal_constructions=(
            *_authority_values(arm)["temporal_constructions"],
            _transition_construction(
                binding, carrier.temporal_evidence, coordinate=coordinate,
            ),
        ),
    )
    compilation = _compilation_with_authority(
        arm, authority, operation_member=BootstrapProposalRetractionV3.create(
            retracted_fact=arm.effect.fact, assertion=arm.effect.fact.assertion,
            retraction_anchor=arm.effect.fact.predicate_anchor,
        ),
    )
    projection = _citation_citing(arm, carrier.transition_id)
    retraction = BootstrapNativeRetractionEffectV3.create(
        kind="retraction",
        retraction=compilation.operation_input.operation_member,
        retracted_targets=(
            _claim_target_binding(arm, claim, role="retracted_target"),
        ),
        transition_records=(transition,), evidence_projections=(projection,),
    )
    records = _materialize(
        SimpleNamespace(planning_records=(
            transition, projection.citation_record, projection.provenance_record,
        )),
        arm.group_request.transaction_group_id, arm.commit_values,
    )
    pairs = _materialized_pairs(SimpleNamespace(evidence_projections=(projection,)), arm.commit_values)
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="retraction transition lacks its retained claim slot key authority",
    ):
        _project(
            arm, history=history, limits=limits, compilation=compilation,
            accepted_effect=retraction, retained_native_records=records,
            evidence_pairs=pairs,
        )
    # A transition kind that differs from its operation arm denies first.
    flipped_carrier, flipped, _flipped_binding = _rebased_transition(
        arm, "retraction", transition_kind="correction",
    )
    assert flipped_carrier.transition_kind == "correction"
    flipped_projection = _citation_citing(arm, flipped_carrier.transition_id)
    flipped_retraction = BootstrapNativeRetractionEffectV3.create(
        kind="retraction",
        retraction=BootstrapProposalRetractionV3.create(
            retracted_fact=arm.effect.fact, assertion=arm.effect.fact.assertion,
            retraction_anchor=arm.effect.fact.predicate_anchor,
        ),
        retracted_targets=(),
        transition_records=(flipped,), evidence_projections=(flipped_projection,),
    )
    flipped_records = _materialize(
        SimpleNamespace(planning_records=(
            flipped, flipped_projection.citation_record,
            flipped_projection.provenance_record,
        )),
        arm.group_request.transaction_group_id, arm.commit_values,
    )
    flipped_pairs = _materialized_pairs(
        SimpleNamespace(evidence_projections=(flipped_projection,)), arm.commit_values,
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="transition kind differs from its operation arm",
    ):
        _project(
            arm, history=history, limits=limits, compilation=compilation,
            accepted_effect=flipped_retraction, retained_native_records=flipped_records,
            evidence_pairs=flipped_pairs,
        )


def _action_carrier(arm: _FactArm) -> ActionRevision:
    """One action revision carrier bound to this native operation.

    The carrier copies the captured claim's accepted temporal evidence and
    decision binding through the real carrier digest recipe; no action planner
    exists yet, so the envelope holds the same retained temporal authority a
    planned action would carry.
    """
    claim = _claim(arm.records)
    body = {
        "record_kind": "action_revision",
        "action_revision_id": "action-revision:envelope",
        "statement_digest": contract_digest(
            b"memorii.semantic-ingestion.statement.v1", "Atlas performs an action.",
        ),
        "operation_id": arm.compilation.operation_id,
        "valid_interval": claim.valid_interval,
        "temporal_evidence": claim.temporal_evidence,
        "temporal_decision_binding": claim.temporal_decision_binding,
        "record_version": 1,
        "codec_fingerprint": claim.codec_fingerprint,
    }
    return ActionRevision.model_validate({
        **body,
        "record_digest": contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1", body,
        ),
    })


def _action_state_proposal(arm: _FactArm):
    fact = arm.effect.fact
    participant = BootstrapProposalActionRoleParticipantV3.create(
        mention_digest=fact.subject_mention_digest, grounding=(fact.assertion,),
    )
    binding = BootstrapProposalActionRoleBindingV3.create(
        role_id="actor", endpoint_kind="actor", participants=(participant,),
    )
    return BootstrapProposalActionStateV3.create(
        action_anchor=fact.predicate_anchor,
        logical_action_digest=contract_digest(
            b"memorii.semantic-ingestion.bootstrap-proposal-logical-action.v3",
            {"action_anchor": fact.predicate_anchor, "role_bindings": (binding,)},
        ),
        role_bindings=(binding,),
        state_id="observed",
        state_anchor=fact.assertion,
        execution_branch=None,
        execution_branch_digest=None,
        assertion=fact.assertion,
        temporal_qualifiers=(),
    )


def _participant_target_binding(
    arm: _FactArm, entity: EntityRevision, *, role_id: str, index: int, mention: str,
):
    """The resolved participant binding at its exact retained mention coordinate."""
    coordinate = contract_digest(
        b"memorii.bootstrap-graph.cluster-reference-coordinate.v3",
        {
            "operation_member_digest": (
                arm.compilation.operation_input.operation_subject.member_digest
            ),
            "path": f"action.{role_id}.{index}",
            "mention_digest": mention,
        },
    )
    return BootstrapNativeTargetBindingV3.create(
        role="action_participant", source_coordinate_digest=coordinate,
        authority=BootstrapSnapshotTargetAuthorityV3.create(
            kind="snapshot",
            target=BootstrapGraphTargetReferenceV3.create(
                record_kind="entity_revision",
                record_id=entity.entity_revision_id,
                record_digest=entity.record_digest,
            ),
            sealed_snapshot_digest="0" * 64, effective_read_set_digest="0" * 64,
            snapshot_record_digest=entity.record_digest,
        ),
    )


def _action_transition_reference(arm: _FactArm, *, to_state_id="observed"):
    authority = arm.compilation.operation_input.planning_construction_authority
    assert authority is not None
    key_values = {
        "from_state_id": "pending",
        "to_state_id": to_state_id,
        "execution_branch_kind": "unbranched",
    }
    applicability = ActionTransitionApplicabilityKey(
        **key_values,
        applicability_key_digest=contract_digest(
            b"memorii.semantic-ingestion.action-transition-applicability.v1",
            key_values,
        ),
    )
    return AcceptedActionTransitionReference(
        transition_rule_id="action-rule:observed",
        applicability_key=applicability,
        action_policy_fingerprint=authority.action_policy_fingerprint,
        resolution_evidence_digest="e" * 64,
    )


def test_action_arm_projects_participants_and_role_binding_envelope(
    tmp_path, monkeypatch, arm,
):
    history, limits = observation_publication(tmp_path, monkeypatch, _SIBLING_ROOTS)
    claim = _claim(arm.records)
    action = _action_carrier(arm)
    proposal = _action_state_proposal(arm)
    subject = _subject_entity(arm.records)
    participant_binding = _participant_target_binding(
        arm, subject, role_id="actor", index=0,
        mention=arm.effect.fact.subject_mention_digest,
    )
    action_planning = BootstrapNativePlanningRecordV3.create(
        operation_execution_id=arm.compilation.operation_execution_id,
        record_kind="action_revision", record_id=action.action_revision_id,
        precondition=AbsentPlanningPrecondition(),
        planning_payload=canonical_planning_payload_from_record(
            action, transaction_group_id=arm.group_request.transaction_group_id,
        ),
        source_member_digest=arm.compilation.operation_input.operation_subject.member_digest,
    )
    projection = _citation_citing(arm, action.action_revision_id)
    entity_planning = tuple(
        record for record in arm.effect.planning_records
        if record.record_kind == "entity_revision"
    )
    citation_planning = (projection.citation_record,)
    provenance_planning = (projection.provenance_record,)
    effect = BootstrapNativeActionStateEffectV3.create(
        kind="action_state", action_state=proposal,
        resolved_participants=(participant_binding,),
        planning_records=(*entity_planning, action_planning, *citation_planning, *provenance_planning),
        terminal_bindings=arm.effect.terminal_bindings,
        evidence_projections=(projection,),
    )
    authority = _rebuild_authority(
        arm, action_transition=_action_transition_reference(arm),
    )
    compilation = _compilation_with_authority(
        arm, authority, operation_member=proposal,
    )
    records = _materialize(
        effect, arm.group_request.transaction_group_id, arm.commit_values,
    )
    pairs = _materialized_pairs(effect, arm.commit_values)
    lookup = {
        record.entity_revision_id: record.logical_entity_id
        for record in records if isinstance(record, EntityRevision)
    }
    stream = _project(
        arm, history=history, limits=limits, compilation=compilation,
        accepted_effect=effect, retained_native_records=records,
        evidence_pairs=pairs, native_entity_lookup=lookup,
    )
    assert [item.record_kind for item in stream] == [
        "action_revision", "citation", "entity_revision", "entity_revision",
        "provenance",
    ]
    action_payload = stream[0].payload
    assert stream[0].primary_key == action.action_revision_id
    assert action_payload.action_revision_id == action.action_revision_id
    assert action_payload.logical_action_id == proposal.logical_action_digest
    assert action_payload.role_bindings == (
        type(action_payload.role_bindings[0])(
            role_id="actor", endpoint_kind="actor",
            entities=(
                ObservedEntityReference(
                    entity_revision_id=subject.entity_revision_id,
                    logical_entity_id=subject.logical_entity_id,
                    reference_path="action_state.role_bindings[].participants[]",
                ),
            ),
        ),
    )
    assert action_payload.action_state == "observed"
    assert action_payload.execution_branch_id is None
    assert action_payload.transition_rule_id == "action-rule:observed"
    assert action_payload.transition_applicability_key_digest == (
        authority.action_transition.applicability_key.applicability_key_digest
    )
    assert action_payload.supporting_claim_assertion_ids == ()
    assert action_payload.valid_interval == claim.valid_interval
    assert action_payload.authenticated_source_interval_evidence == (
        next(
            candidate.authenticated_source_interval_evidence
            for candidate in claim.temporal_evidence.decision_closure.candidates
            if candidate.candidate_id
            in claim.temporal_evidence.decision_closure.selected_candidate_ids
        )
    )
    assert action_payload.temporal_decision_binding == action.temporal_decision_binding
    assert action_payload.system_interval == TimeInterval(start=TEST_NOW)
    assert action_payload.source_ids == (authority.source_id,)
    assert action_payload.provenance_ids == (pairs[0][1].provenance_id,)
    assert action_payload.boundary is False
    assert _HEX64.fullmatch(stream[0].record_digest)
    assert stream[0].record_digest == action_payload.record_digest

    # The captured fact authority retains no action transition: typed refusal.
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="action revision lacks its retained action transition authority",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(arm, _rebuild_authority(arm), operation_member=proposal),
            accepted_effect=effect, retained_native_records=records,
            evidence_pairs=pairs, native_entity_lookup=lookup,
        )
    # An applicability key that does not bind the retained action state denies.
    mismatched = _rebuild_authority(
        arm, action_transition=_action_transition_reference(arm, to_state_id="other"),
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="action transition applicability does not bind the retained action state",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(arm, mismatched, operation_member=proposal),
            accepted_effect=effect, retained_native_records=records,
            evidence_pairs=pairs, native_entity_lookup=lookup,
        )
    # A participant whose mention coordinate resolves to no exact entity
    # target denies instead of guessing an entity.
    foreign = effect.model_copy(update={"resolved_participants": ()})
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="action role participant does not resolve to one exact entity target",
    ):
        _project(
            arm, history=history, limits=limits, compilation=compilation,
            accepted_effect=foreign, retained_native_records=records,
            evidence_pairs=pairs, native_entity_lookup=lookup,
        )
    # An action arm that retains claims keeps its exact claim-projection
    # pairing, but a retained claim still needs its polarity authority: the
    # action envelope retains no fact member, so the claim emission is a typed
    # refusal rather than a guessed polarity.
    claim_planning = tuple(
        record for record in arm.effect.planning_records
        if record.record_kind in {"claim_assertion", "claim_projection", "relation_revision"}
    )
    with_claims = _recreate(
        effect, planning_records=(
            *entity_planning, *claim_planning, action_planning,
            *citation_planning, *provenance_planning,
        ),
    )
    claim_records = _materialize(
        with_claims, arm.group_request.transaction_group_id, arm.commit_values,
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="claim polarity lacks its retained operation authority",
    ):
        _project(
            arm, history=history, limits=limits, compilation=compilation,
            accepted_effect=with_claims, retained_native_records=claim_records,
            evidence_pairs=pairs, native_entity_lookup=lookup,
        )


def _identity_envelope(arm: _FactArm):
    """Build one real identity materialization envelope around a rekey.

    The chain uses only real constructors: the terminal fixture seals one
    identity operation with its transition-role binding, the production
    identity-lineage compiler inputs compile a rekey transition (one
    historical reference closure entry with its disposition), the graph
    planning owner freezes the nonpublishing planning result, and the
    bootstrap materialization contract retains the lineage, successor and
    disposition planning records.  The carriers are then rebound to this
    native operation exactly like the correction/retraction feasibility.
    """
    authority = arm.compilation.operation_input.planning_construction_authority
    assert authority is not None
    span = authority.evidence_constructions[0].source_span
    evidence = (LineageEvidenceReference(
        source_id=span.source_id, start=span.segment_local_span.start,
        end=span.segment_local_span.end, evidence_digest="4" * 64,
    ),)
    predecessor = LineageEntityIdentity(
        entity_revision_id="entity-revision:alice:v1", logical_entity_id="entity:alice",
    )
    successor = LineageEntityIdentity(
        entity_revision_id="entity-revision:alice:v2", logical_entity_id="entity:alice",
    )
    reference = LineageReverseReference.create(
        record_kind="claim_projection", record_id="claim-projection:referencing",
        reference_path="subject_entity_revision_id", predecessor=predecessor,
        lifecycle="historical", base_record_digest="5" * 64,
        referenced_value_digest="6" * 64,
    )
    disposition = LineageReferenceDisposition.create(
        reference_digest=reference.reference_digest,
        record_kind=reference.record_kind, record_id=reference.record_id,
        reference_path=reference.reference_path, predecessor=predecessor,
        disposition="preserve_historical", successors=(),
        source_evidence=evidence, basis="operation_defined_history_preservation",
    )
    fixture = accepted_terminal(
        operation_id="op:identity-envelope", operation_kind="identity",
        identity_lineage_compiler=SimpleNamespace(
            compile_transition=lambda operation, candidate, source_analysis: (
                CompiledIdentityLineageTransition.create(
                    operation_id=operation.operation_id, operation="rekey",
                    predecessors=(predecessor,), successors=(successor,),
                    graph_revision_before="genesis", recorded_at=None,
                    lineage_snapshot_before_digest=identity_lineage_genesis_digest(
                        "semantic_ingestion",
                    ),
                    source_evidence=evidence,
                    reverse_reference_closure=(reference,),
                    reference_dispositions=(disposition,),
                )
            ),
        ),
    )
    sealed = fixture.sealed_operations[0]
    candidate = fixture.candidates[0]
    analysis = fixture.source_analyses[0]
    accepted = AcceptedIdentityOperation.create(
        operation_id=sealed.operation_id, operation="rekey",
        predecessors=(predecessor,), successors=(successor,),
        source_evidence=evidence, reference_assignments=(),
    )
    state = SemanticReplayState.genesis("semantic_ingestion")
    reader = _Reader(state, bootstrap_reference_integrity(state, completed_at=TEST_NOW))
    snapshot = SemanticIngestionTransactionCoordinator(
        reader, now_provider=lambda: TEST_NOW,
    ).acquire_snapshot()
    decision = TrustedAcceptedIdentityOperationDecision.create(
        operation=accepted, alias_payload=None,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
        operation_fence_binding_digest="f" * 64,
        graph_snapshot_digest=snapshot.snapshot_digest,
        graph_read_set_digest=snapshot.read_set.read_set_digest,
        authority_digest="7" * 64,
    )
    verification = VerifiedIdentityDecisionAuthority.create(
        decision_digest=decision.decision_digest,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
        operation_fence_binding_digest="f" * 64,
        graph_snapshot_digest=snapshot.snapshot_digest,
        graph_read_set_digest=snapshot.read_set.read_set_digest,
        authority_record_id="authority:identity-envelope",
        authority_record_digest="9" * 64, verifier_id="verifier",
    )
    artifact = _identity_artifact(
        accepted,
        sealed_operation_digest=sealed.sealed_operation_digest,
        candidate_digest=candidate.candidate_digest,
        source_analysis_digest=analysis.analysis_digest,
    ).model_copy(update={
        # The accepted artifact must carry the exact computed decision and
        # verification identities the frozen artifact re-checks.
        "authority_digest": verification.verification_digest,
        "verified_decision_digest": decision.decision_digest,
        "authority_verification_digest": verification.verification_digest,
        "authority_record_id": "authority:identity-envelope",
        "authority_record_digest": "9" * 64,
    })
    from memorii.core.memory_evolution.graph_records import (
        AcceptedIdentityOperationArtifact,
    )
    artifact = AcceptedIdentityOperationArtifact.create(**{
        name: getattr(artifact, name) for name in type(artifact).model_fields
        if name != "artifact_digest"
    })
    fixture_transition = next(
        item.transition for item in fixture.accepted_carriers
        if isinstance(item, IdentityLineageRecord)
    )
    state_before = GraphPlanningState.create(
        base_snapshot_digest=snapshot.canonical_graph.snapshot_digest, records=(),
        codec_manifest_fingerprint=canonical_graph_codec_manifest().manifest_fingerprint,
        applied_planned_delta_digests=(),
    )
    frozen = build_frozen_identity_graph_planning_artifact_from_state(
        sealed_graph_snapshot=snapshot,
        transaction_group_id=arm.group_request.transaction_group_id,
        current_planning_state=state_before,
        accepted_operation_artifact=artifact,
        compiled_transition=fixture_transition,
        operation=sealed, candidate=candidate,
        trusted_decision=decision, authority_verification=verification,
    )
    nonpublishing = NonPublishingIdentityPlanningResultV3.create(
        transaction_group_id=arm.group_request.transaction_group_id,
        sealed_graph_snapshot_digest=snapshot.snapshot_digest,
        graph_read_set_digest=snapshot.read_set.read_set_digest,
        planning_state_before_digest=state_before.state_digest,
        frozen_artifact=frozen,
        planning_state_after=frozen.planning_state_after,
    )
    allocation = BootstrapCanonicalIdentityBindingAllocationAuthorityV3.create(
        source_id=authority.source_id, source_digest=authority.source_digest,
        preparation_fingerprint=authority.preparation_fingerprint,
        recovery_key_digest="1" * 64, sealed_snapshot_digest=snapshot.snapshot_digest,
        effective_read_set_digest=snapshot.read_set.read_set_digest,
        authority_base_planning_state_digest=state_before.state_digest,
        required_scope_set_digest="2" * 64,
        authorized_scope_identity="scope:identity-envelope",
        allocation_namespace_id="identity-envelope",
        source_operation_memberships=(), referenced_cluster_ids=(),
        cluster_decisions=(), first_use_dependencies=(),
    )
    reload = BootstrapCanonicalIdentityBindingAllocationReloadV3.create(
        authority=allocation, source_plan_checkpoint_digest="b" * 64,
        publication_generation_digest="c" * 64,
    )
    # Rebind the fixture's real identity carrier to this native operation.
    carrier = next(
        item for item in fixture.accepted_carriers
        if isinstance(item, IdentityLineageRecord)
    )
    original_binding = carrier.temporal_decision_binding
    attachment = type(original_binding.temporal_attachment).create(**{
        **{name: getattr(original_binding.temporal_attachment, name)
           for name in type(original_binding.temporal_attachment).model_fields
           if name != "binding_digest"},
        "operation_id": arm.compilation.operation_id,
    })
    binding = type(original_binding).create(**{
        **{name: getattr(original_binding, name)
           for name in type(original_binding).model_fields
           if name != "binding_digest"},
        "operation_id": arm.compilation.operation_id,
        "temporal_attachment": attachment,
    })
    rebased_transition = CompiledIdentityLineageTransition.create(**{
        name: value for name, value in {
            "operation_id": arm.compilation.operation_id, "operation": "rekey",
            "predecessors": (predecessor,), "successors": (successor,),
            "graph_revision_before": "genesis", "recorded_at": None,
            "lineage_snapshot_before_digest": identity_lineage_genesis_digest(
                "semantic_ingestion",
            ),
            "source_evidence": evidence,
            "reverse_reference_closure": (reference,),
            "reference_dispositions": (disposition,),
        }.items()
    })
    body = carrier.model_dump(mode="python", exclude={"record_digest"}) | {
        "operation_id": arm.compilation.operation_id,
        "statement_digest": rebased_transition.transition_digest,
        "transition": rebased_transition.model_dump(mode="python"),
        "temporal_decision_binding": binding.model_dump(mode="python"),
    }
    rebased_carrier = IdentityLineageRecord.model_validate({
        **body,
        "record_digest": contract_digest(
            b"memorii.semantic-ingestion.temporal-carrier.v1", body,
        ),
    })
    successor_entity = EntityRevision.create(
        operation_id=arm.compilation.operation_id,
        entity_revision_id=successor.entity_revision_id,
        logical_entity_id=successor.logical_entity_id,
        lifecycle="active", source_evidence=evidence,
        codec_fingerprint=_codec("entity_revision"),
    )
    disposition_record = ReferenceDispositionRecord.create(
        operation_id=arm.compilation.operation_id,
        codec_fingerprint=_codec("reference_disposition"),
        reference_disposition_id=disposition.disposition_digest,
        target_record_kind=reference.record_kind, target_record_id=reference.record_id,
        target_reference_path=reference.reference_path,
        predecessor_entity_revision_id=predecessor.entity_revision_id,
        predecessor_logical_entity_id=predecessor.logical_entity_id,
        successor_entity_revision_ids=(),
        successor_logical_entity_ids=(),
        disposition=disposition.disposition,
        basis=disposition.basis, source_evidence=evidence,
    )
    def _planning(record):
        return BootstrapNativePlanningRecordV3.create(
            operation_execution_id=arm.compilation.operation_execution_id,
            record_kind=record.record_kind, record_id=graph_record_id(record),
            precondition=AbsentPlanningPrecondition(),
            planning_payload=canonical_planning_payload_from_record(
                record, transaction_group_id=arm.group_request.transaction_group_id,
            ),
            source_member_digest=arm.compilation.operation_input.operation_subject.member_digest,
        )
    lineage_planning = _planning(rebased_carrier)
    materialization = BootstrapNativeIdentityMaterializationV3.create(
        canonical_identity_authority=reload,
        graph_free_identity_input_digest="d" * 64,
        fresh_planning_result=nonpublishing,
        revision_and_alias_records=(_planning(successor_entity),),
        lineage_record=lineage_planning,
        reference_disposition_records=(_planning(disposition_record),),
    )
    identity_member = BootstrapProposalIdentityOperationV3.create(
        operation="rekey",
        predecessor_mention_digests=(arm.effect.fact.subject_mention_digest,),
        successor_mention_digests=(arm.effect.fact.subject_mention_digest,),
        reference_assignments=(), assertion=arm.effect.fact.assertion,
        identity_anchor=arm.effect.fact.predicate_anchor,
    )
    return {
        "carrier": rebased_carrier, "binding": binding,
        "transition": rebased_transition, "reference": reference,
        "disposition": disposition, "evidence": evidence,
        "successor_entity": successor_entity,
        "disposition_record": disposition_record,
        "materialization": materialization, "identity_member": identity_member,
        "lineage_planning": lineage_planning,
    }


def test_identity_arm_projects_lineage_and_reference_disposition_envelope(
    tmp_path, monkeypatch, arm,
):
    history, limits = observation_publication(tmp_path, monkeypatch, _SIBLING_ROOTS)
    envelope = _identity_envelope(arm)
    carrier = envelope["carrier"]
    binding = envelope["binding"]
    coordinate = _certified_coordinate(arm, carrier.temporal_evidence)
    identity_authority = _rebuild_authority(
        arm, arbitration_policy_bundle=None,
        temporal_constructions=(
            *_authority_values(arm)["temporal_constructions"],
            _transition_construction(
                binding, carrier.temporal_evidence, coordinate=coordinate,
            ),
        ),
        identity_construction=BootstrapNativeIdentityConstructionAuthorityV3.create(
            graph_free_identity_input_digest="1" * 64,
            authority_record_id="authority:identity-envelope",
            authority_record_digest="2" * 64, verifier_id="verifier",
            semantic_authorization_read_set_digest="3" * 64,
            identity_policy_fingerprint="4" * 64,
            operation_fence_id="identity-fence:envelope",
            operation_fence_binding_digest="5" * 64,
        ),
    )
    compilation = _compilation_with_authority(
        arm, identity_authority, operation_member=envelope["identity_member"],
    )
    projection = _citation_citing(arm, carrier.identity_lineage_id)
    effect = BootstrapNativeIdentityEffectV3.create(
        kind="identity",
        identity_operation=envelope["identity_member"],
        materialization=envelope["materialization"],
        target_bindings=(), terminal_bindings=arm.effect.terminal_bindings,
        evidence_projections=(projection,),
    )
    materialization = envelope["materialization"]
    records = _materialize(
        SimpleNamespace(planning_records=(
            *materialization.revision_and_alias_records,
            materialization.lineage_record,
            *materialization.reference_disposition_records,
            projection.citation_record,
            projection.provenance_record,
        )),
        arm.group_request.transaction_group_id, arm.commit_values,
    )
    pairs = _materialized_pairs(effect, arm.commit_values)
    lookup = dict(arm.lookup) | {
        envelope["successor_entity"].entity_revision_id:
            envelope["successor_entity"].logical_entity_id,
        "entity-revision:alice:v1": "entity:alice",
    }
    stream = _project(
        arm, history=history, limits=limits, compilation=compilation,
        accepted_effect=effect, retained_native_records=records,
        evidence_pairs=pairs, native_entity_lookup=lookup,
    )
    assert [item.record_kind for item in stream] == [
        "citation", "entity_revision", "identity_transition", "provenance",
        "reference_disposition",
    ]
    identity_payload = stream[2].payload
    assert stream[2].primary_key == carrier.identity_lineage_id
    assert identity_payload.transition_id == carrier.identity_lineage_id
    assert identity_payload.operation == "rekey"
    assert identity_payload.predecessor_entities == (
        ObservedEntityReference(
            entity_revision_id="entity-revision:alice:v1",
            logical_entity_id="entity:alice",
            reference_path="transition.predecessors[].entity_revision_id",
        ),
    )
    assert identity_payload.successor_entities == (
        ObservedEntityReference(
            entity_revision_id=envelope["successor_entity"].entity_revision_id,
            logical_entity_id=envelope["successor_entity"].logical_entity_id,
            reference_path="transition.successors[].entity_revision_id",
        ),
    )
    assert identity_payload.effective_time.kind == "certified_text_time"
    assert identity_payload.effective_time.evidence_spans == coordinate.evidence_spans
    assert identity_payload.transition_temporal_evidence == carrier.temporal_evidence
    assert identity_payload.transition_temporal_decision_binding == binding
    assert identity_payload.system_interval == TimeInterval(start=TEST_NOW)
    assert identity_payload.source_evidence == coordinate.evidence_spans
    assert identity_payload.operation_id == arm.compilation.operation_id
    assert identity_payload.boundary is False
    assert _HEX64.fullmatch(stream[2].record_digest)
    assert stream[2].record_digest == identity_payload.record_digest

    disposition_payload = stream[4].payload
    disposition_record = envelope["disposition_record"]
    assert stream[4].primary_key == disposition_record.reference_disposition_id
    assert disposition_payload.disposition_id == (
        disposition_record.reference_disposition_id
    )
    assert disposition_payload.transition_id == carrier.identity_lineage_id
    assert disposition_payload.record_kind == "claim_projection"
    assert disposition_payload.record_id == envelope["reference"].record_id
    assert disposition_payload.reference_path == envelope["reference"].reference_path
    assert disposition_payload.predecessor_entity == ObservedEntityReference(
        entity_revision_id="entity-revision:alice:v1",
        logical_entity_id="entity:alice",
        reference_path="predecessor_entity_revision_id",
    )
    assert disposition_payload.successor_entities == ()
    assert disposition_payload.disposition == "preserve_historical"
    assert disposition_payload.evidence_ids == ("4" * 64,)
    assert disposition_payload.system_interval == TimeInterval(start=TEST_NOW)
    assert disposition_payload.boundary is False
    assert _HEX64.fullmatch(stream[4].record_digest)

    # Without its retained identity construction the arm is a typed refusal.
    stripped = _rebuild_authority(
        arm, arbitration_policy_bundle=None,
        temporal_constructions=(
            *_authority_values(arm)["temporal_constructions"],
            _transition_construction(
                binding, carrier.temporal_evidence, coordinate=coordinate,
            ),
        ),
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="identity arm lacks its retained identity construction",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(
                arm, stripped, operation_member=envelope["identity_member"],
            ),
            accepted_effect=effect, retained_native_records=records,
            evidence_pairs=pairs, native_entity_lookup=lookup,
        )
    # Lineage source evidence that resolves to no complete retained span denies.
    unresolvable_authority = _rebuild_authority(
        arm, arbitration_policy_bundle=None, evidence_constructions=(),
        temporal_constructions=(
            *_authority_values(arm)["temporal_constructions"],
            _transition_construction(
                binding, carrier.temporal_evidence, coordinate=coordinate,
            ),
        ),
        identity_construction=identity_authority.identity_construction,
    )
    with pytest.raises(
        NativeGraphObservationProjectionError,
        match="no complete retained source span",
    ):
        _project(
            arm, history=history, limits=limits,
            compilation=_compilation_with_authority(
                arm, unresolvable_authority,
                operation_member=envelope["identity_member"],
            ),
            accepted_effect=effect, retained_native_records=records,
            evidence_pairs=pairs, native_entity_lookup=lookup,
        )


# --- Observed temporal/trust claim projections from retained publications ---
#
# The projection-record producer is exercised against a real published
# projection history (two generations, temporal and trust) reconstructed from
# the same detached memory-plane snapshot, mirroring the detached authority.
# Every denial below keeps a passing control in the same test that proves the
# guard is load-bearing for exactly the guarded condition.


_PROJECTION_ROOTS = (
    "ProjectionObservationIdentity", "ObservedTemporalClaimProjection",
    "ObservedTrustClaimProjection",
)


def _published_history(tmp_path, monkeypatch, *, publications: int):
    """Publish real temporal/trust generations and detach their authority."""
    from tests.unit.core.test_projection_history import (
        T0 as HISTORY_T0,
    )
    from tests.unit.core.test_projection_history import (
        _Clock,
        _repository,
        _request,
    )

    clock = _Clock(*(
        HISTORY_T0 + timedelta(hours=index + 1) for index in range(publications)
    ))
    harness = _repository(tmp_path / "projection-history", clock)
    for operation in range(1, publications + 1):
        harness.install(_request(
            operation, outcome="contested" if operation == 1 else "pass",
        ))
    revision, records = harness.plane.read_write_snapshot()
    from memorii.core.memory_evolution.projection_history import (
        ProjectionHistoryRepository,
    )
    from memorii.core.memory_plane.service import MemoryPlaneService
    from memorii.core.memory_plane.store import ReadOnlyMemoryPlaneSnapshotStore

    detached = ProjectionHistoryRepository(
        MemoryPlaneService(record_store=ReadOnlyMemoryPlaneSnapshotStore(
            write_revision=revision, records=records,
        )),
        repository_id="semantic_ingestion",
    )
    return harness, detached


def _project_publications(
    published, projection_history, *,
    view="current", valid_at=None, system_as_of=None, graph_revision=None,
):
    """Project one retained projection history under a published registry.

    ``published`` is the ``observation_publication`` fixture result.
    """
    from memorii.core.memory_evolution.graph_observation_materialization import (
        project_observed_claim_projections,
    )
    from tests.unit.core.test_projection_history import T0 as HISTORY_T0

    history, limits = published
    return project_observed_claim_projections(
        projection_history=projection_history, view=view, valid_at=valid_at,
        system_as_of=system_as_of or HISTORY_T0 + timedelta(days=1),
        graph_revision=graph_revision or "graph-revision-2",
        history=history,
        publication=history.publications[0],
        limits=limits,
    )


def _projection_kind(record_kind: str) -> str:
    return (
        "temporal" if record_kind == "temporal_claim_projection" else "trust"
    )


def test_current_view_emits_projection_records_from_active_publications(
    tmp_path, monkeypatch,
):
    published = observation_publication(
        tmp_path, monkeypatch, _PROJECTION_ROOTS,
    )
    harness, detached = _published_history(tmp_path, monkeypatch, publications=2)
    active_temporal = detached.active_temporal_authority()
    active_trust = detached.active_trust_authority()
    selection = _project_publications(published, detached)

    assert selection.temporal_generation_digest == (
        active_temporal.pointer.generation_digest
    )
    assert selection.temporal_pointer_digest == active_temporal.pointer.pointer_digest
    assert selection.trust_generation_digest == active_trust.pointer.generation_digest
    assert selection.trust_pointer_digest == active_trust.pointer.pointer_digest
    assert [item.record_kind for item in selection.records] == [
        "temporal_claim_projection", "trust_claim_projection",
    ]
    from memorii.core.memory_evolution.observation_activation_runtime import (
        derive_projection_observation_identity,
    )

    for item, view in (
        (selection.records[0], active_temporal),
        (selection.records[1], active_trust),
    ):
        payload = item.payload
        assert payload.projection == view.projections[-1]
        assert payload.generation_digest == view.pointer.generation_digest
        assert payload.publication_pointer == view.pointer
        assert payload.successor_publication_pointer is None
        assert payload.boundary is True
        assert item.primary_key == payload.observation_id
        assert item.record_digest == payload.record_digest
        assert _HEX64.fullmatch(payload.record_digest)
        # The outward identity is the registered derived identity, never a
        # hand-set value.
        assert payload.observation_id == derive_projection_observation_identity(
            _projection_kind(item.record_kind),
            payload.projection.repository_id, payload.generation_digest,
            payload.projection.projection_digest,
            history=published[0],
            publication=published[0].publications[0],
            limits=published[1],
        )


def test_historical_view_selects_publication_at_system_time_with_successor(
    tmp_path, monkeypatch,
):
    from tests.unit.core.test_projection_history import T0 as HISTORY_T0

    published = observation_publication(
        tmp_path, monkeypatch, _PROJECTION_ROOTS,
    )
    harness, detached = _published_history(tmp_path, monkeypatch, publications=2)
    first_temporal = detached.historical_temporal(
        system_as_of=HISTORY_T0 + timedelta(hours=1)
    )
    second_temporal = detached.historical_temporal(
        system_as_of=HISTORY_T0 + timedelta(hours=2)
    )
    selection = _project_publications(
        published, detached, view="historical",
        valid_at=HISTORY_T0 + timedelta(minutes=30),
        system_as_of=HISTORY_T0 + timedelta(hours=1, minutes=30),
    )
    temporal_payload = selection.records[0].payload
    assert selection.temporal_pointer_digest == (
        first_temporal.pointer.pointer_digest
    )
    assert temporal_payload.publication_pointer == first_temporal.pointer
    # The immediately following same-kind pointer is retained as successor.
    assert temporal_payload.successor_publication_pointer == (
        second_temporal.pointer
    )
    assert temporal_payload.projection.projection_digest == (
        first_temporal.projections[-1].projection_digest
    )
    trust_payload = selection.records[1].payload
    assert trust_payload.successor_publication_pointer is not None
    assert trust_payload.successor_publication_pointer.pointer_digest != (
        trust_payload.publication_pointer.pointer_digest
    )


def test_view_and_valid_time_combinations_deny_with_controls(tmp_path, monkeypatch):
    from tests.unit.core.test_projection_history import T0 as HISTORY_T0

    published = observation_publication(
        tmp_path, monkeypatch, _PROJECTION_ROOTS,
    )
    _, detached = _published_history(tmp_path, monkeypatch, publications=2)
    from memorii.core.memory_evolution.graph_observation_paging import (
        ObservationCohortUnavailableError,
    )

    with pytest.raises(
        ObservationCohortUnavailableError,
        match="current projection view cannot select a valid time",
    ):
        _project_publications(
            published, detached, view="current",
            valid_at=HISTORY_T0,
        )
    # Control: the same authority with no valid time emits.
    assert _project_publications(published, detached).records
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="historical projection view requires a valid time",
    ):
        _project_publications(
            published, detached, view="historical", valid_at=None,
        )
    # Control: the same authority with a valid time emits historical records.
    assert _project_publications(
        published, detached, view="historical",
        valid_at=HISTORY_T0, system_as_of=HISTORY_T0 + timedelta(days=1),
    ).records
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="no exact publication selection recipe",
    ):
        _project_publications(
            published, detached, view="lineage", valid_at=None,
        )


def test_absent_history_allows_null_pairs_only_for_current_view(
    tmp_path, monkeypatch,
):
    from tests.unit.core.test_projection_history import T0 as HISTORY_T0

    published = observation_publication(
        tmp_path, monkeypatch, _PROJECTION_ROOTS,
    )
    harness, detached = _published_history(tmp_path, monkeypatch, publications=0)
    empty = _project_publications(published, detached)
    # Before the first projection generation the cohort remains observable
    # with null pairs and no projection records.
    assert empty.records == ()
    assert empty.temporal_generation_digest is None
    assert empty.temporal_pointer_digest is None
    assert empty.trust_generation_digest is None
    assert empty.trust_pointer_digest is None
    from memorii.core.memory_evolution.graph_observation_paging import (
        ObservationCohortUnavailableError,
    )

    # A historical view denies when no publication exists at its coordinate.
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="selected projection publication is not retained in the detached image",
    ):
        _project_publications(
            published, detached, view="historical",
            valid_at=HISTORY_T0, system_as_of=HISTORY_T0,
        )


def test_stale_active_generation_denies_current_view_with_control(
    tmp_path, monkeypatch,
):
    published = observation_publication(
        tmp_path, monkeypatch, _PROJECTION_ROOTS,
    )
    _, detached = _published_history(tmp_path, monkeypatch, publications=2)
    from memorii.core.memory_evolution.graph_observation_paging import (
        ObservationCohortUnavailableError,
    )

    with pytest.raises(
        ObservationCohortUnavailableError,
        match="active temporal projection generation does not bind the requested graph",
    ):
        _project_publications(
            published, detached, graph_revision="graph-revision-1",
        )
    # Control: the active generations bind the requested revision.
    assert _project_publications(published, detached).records


def test_asymmetric_projection_history_denies_with_control(tmp_path, monkeypatch):
    """One kind's retained history cannot stand in for the other's absence."""
    from memorii.core.memory_evolution.graph_observation_paging import (
        ObservationCohortUnavailableError,
    )
    from memorii.core.memory_evolution.projection_history import (
        ProjectionHistoryRepository,
    )
    from memorii.core.memory_plane.service import MemoryPlaneService
    from memorii.core.memory_plane.store import ReadOnlyMemoryPlaneSnapshotStore

    published = observation_publication(
        tmp_path, monkeypatch, _PROJECTION_ROOTS,
    )
    harness, detached = _published_history(tmp_path, monkeypatch, publications=2)
    revision, records = harness.plane.read_write_snapshot()
    asymmetric = ProjectionHistoryRepository(
        MemoryPlaneService(record_store=ReadOnlyMemoryPlaneSnapshotStore(
            write_revision=revision,
            records=tuple(
                record for record in records
                if not record.source_kind.startswith("semantic_projection_trust")
            ),
        )),
        repository_id="semantic_ingestion",
    )
    with pytest.raises(
        ObservationCohortUnavailableError,
        match="selected projection publication is not retained in the detached image",
    ):
        _project_publications(published, asymmetric)
    # Control: the complete detached image of the same snapshot emits.
    assert _project_publications(published, detached).records


def test_identity_root_absent_denies_emission_with_control(tmp_path, monkeypatch):
    """A publication without the identity root never receives hand-set identities."""
    published = observation_publication(
        tmp_path, monkeypatch,
        ("ObservedTemporalClaimProjection", "ObservedTrustClaimProjection"),
    )
    harness, detached = _published_history(tmp_path, monkeypatch, publications=2)
    from memorii.core.memory_evolution.graph_observation_paging import (
        ObservationCohortUnavailableError,
    )

    with pytest.raises(
        ObservationCohortUnavailableError,
        match="projection observation identity root is not selected",
    ):
        _project_publications(published, detached)
    # Control: the same retained authority emits under a publication with the
    # identity root.
    with_identity = observation_publication(
        tmp_path / "identity", monkeypatch, _PROJECTION_ROOTS,
    )
    assert _project_publications(with_identity, detached).records


def test_successor_pointer_join_guards(tmp_path, monkeypatch):
    """An unknown pointer digest denies; the retained successor join is exact."""
    from memorii.core.memory_evolution.projection_history import (
        ProjectionHistoryError,
    )
    from tests.unit.core.test_projection_history import T0 as HISTORY_T0

    _, detached = _published_history(tmp_path, monkeypatch, publications=2)
    active = detached.active_temporal_authority()
    successor = detached.publication_successor(
        "temporal", active.pointer.pointer_digest
    )
    assert successor is None  # the tip has no successor
    historical = detached.historical_temporal(
        system_as_of=HISTORY_T0 + timedelta(hours=1)
    )
    assert historical.pointer.pointer_digest != active.pointer.pointer_digest
    assert detached.publication_successor(
        "temporal", historical.pointer.pointer_digest
    ) == active.pointer
    with pytest.raises(ProjectionHistoryError):
        detached.publication_successor("temporal", "0" * 64)
