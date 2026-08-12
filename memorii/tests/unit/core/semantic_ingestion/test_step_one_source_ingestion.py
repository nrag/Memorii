import base64
import json
from datetime import UTC, datetime
from hashlib import sha256

import pytest
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, source_admission_source_digest
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    AuthenticatedStructuredSourceEnvelope,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    decode_typed_value,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import ExtractionTriggerMode, MemoryScope
from memorii.core.memory_evolution.record_projection import source_observation_from_record
from memorii.core.memory_evolution.source_admission import (
    DelegationResultSourceEnvelope,
    GovernedConversationSnapshotInput,
    GovernedMessageSemanticContext,
    ProviderEnvelopeMessage,
    ProviderEventNormalizer,
    SourceAdmissionRequest,
    build_admitted_source_record,
    build_structured_step_one_material_from_governance,
    build_verbatim_step_one_material,
    step_one_source_digest,
)
from memorii.core.memory_evolution.source_governance import (
    AdmissionScopeAuthorizationProof,
    derive_source_governance_material,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    MessageAdmissionCarrierSet,
    MessageAdmissionIdentity,
    SegmentGovernanceBinding,
    SegmentGovernanceCarrierSet,
    SourceSemanticContext,
)
from memorii.core.semantic_ingestion.contracts import (
    RequiredOutcomeScopeSet as SemanticRequiredOutcomeScopeSet,
)
from memorii.domain.enums import SourceModality


def _values(text: str = "Atlas owner is Bob."):
    binding = DeliveryPrincipalBinding.create(
        principal_subject_id="principal:alice", tenant_partition_id="tenant:one", provider_identity="provider:test"
    )
    ingress_scopes = RequiredOutcomeScopeSet.create(tenant_partition_id="tenant:one", scopes={"session:one"})
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=binding, required_outcome_scopes=ingress_scopes,
        current_authorized_scopes=ingress_scopes,
    )
    identity = DeliveryIdentity.create(binding, "event-1")
    request = SourceAdmissionRequest(
        delivery_identity=identity, delivery_key_digest=identity.delivery_key_digest,
        required_outcome_scopes=ingress_scopes, source_kind="conversation_turn", original_text=text,
    )
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    source_digest = step_one_source_digest(
        source_id=source_id, delivery_key_digest=identity.delivery_key_digest, original_text=text,
    )
    scopes = SemanticRequiredOutcomeScopeSet.create(
        tenant_partition_id="tenant:one", scopes=(MemoryScope(session_id="session:one"),)
    )
    governance = SegmentGovernanceBinding.create(
        source_id=source_id, segment_id="segment-0", message_semantic_context_digest="1" * 64,
        effective_scope_digest="2" * 64, authority_digest="3" * 64, data_classification="internal",
        modality=SourceModality.ASSERTION, provider_egress_decision_digest="4" * 64,
        egress_disposition="allow_verbatim",
    )
    carriers = SegmentGovernanceCarrierSet.create(source_id=source_id, bindings=(governance,))
    admission = MessageAdmissionIdentity.create(
        delivery_principal_binding_digest=binding.binding_digest, authenticated_source_reference="event-1",
        authenticated_source_reference_key_digest="5" * 64,
        message_bytes_digest=sha256(text.encode()).hexdigest(),
        segment_governance_binding_digest=governance.binding_digest,
    )
    admissions = MessageAdmissionCarrierSet.create(source_id=source_id, identities=(admission,))
    artifact = GovernanceCarrierArtifact.create(
        artifact_id="governance-1", atomic_generation=1, segment_governance=carriers,
        message_admissions=admissions, required_outcome_scopes=scopes,
    )
    context = SourceSemanticContext.create(
        source_id=source_id, source_digest=source_digest, trigger_mode=ExtractionTriggerMode.IMMEDIATE,
        provenance_digest="6" * 64, temporal_references=(), received_at=datetime(2026, 1, 1, tzinfo=UTC),
        retained_at=datetime(2026, 1, 1, tzinfo=UTC), source_effective_interval_evidence=None,
        provider_egress_policy_fingerprint="7" * 64, governance_policy_fingerprint="8" * 64,
        trust_policy_fingerprint="9" * 64,
    )
    proof = AdmissionScopeAuthorizationProof.create(
        delivery_principal_binding_digest=binding.binding_digest,
        required_outcome_scope_set_digest=ingress_scopes.required_scope_set_digest,
        current_authorized_scope_set_digest=ingress_scopes.required_scope_set_digest,
        session_authorization_evidence_digest="a" * 64, decision="authorized",
        authorized_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    material = build_verbatim_step_one_material(
        source_id=source_id, source_digest=source_digest, original_text=text,
        required_outcome_scopes=scopes, semantic_context=context,
        segment_governance_carriers=carriers, message_admission_carriers=admissions,
        governance_carrier_artifact=artifact, admission_scope_authorization_proof=proof,
        source_reference="event-1",
    )
    record = build_admitted_source_record(
        request=request, source_id=source_id, retained_at=datetime(2026, 1, 1, tzinfo=UTC), material=material,
        session_id="session:one",
    )
    return record, request, ingress, identity


def test_step_one_verbatim_source_round_trips_and_admits_atomically() -> None:
    record, _, ingress, identity = _values()
    assert source_admission_source_digest(record) == step_one_source_digest(
        source_id=record.memory_id, delivery_key_digest=identity.delivery_key_digest, original_text=record.text,
    )
    observation = source_observation_from_record(record)
    assert observation.is_step_one_admitted
    assert observation.semantic_text_projection.projection_text == record.text

    service = GovernedSourceAdmissionService(MemoryPlaneService())
    accepted = service.prepare_atomic(source=record, delivery_identity=identity, ingress=ingress, operation_id="operation-1").accepted
    assert accepted.observation.is_step_one_admitted


def test_step_one_rejects_governance_and_text_substitution_on_reload() -> None:
    record, _, _, _ = _values()
    body = record.model_copy(deep=True)
    material = decode_typed_value(base64.b64decode(body.content["source_admission"]["step_one_material_ctv"]))
    material["semantic_text_projection"]["projection_text"] = "substituted"
    body.content["source_admission"]["step_one_material_ctv"] = base64.b64encode(encode_typed_value(material)).decode("ascii")
    with pytest.raises(ValueError, match="invalid|substituted|mismatch"):
        source_observation_from_record(body)


def _governed_ingress() -> AuthenticatedIngressContext:
    _, _, ingress, _ = _values()
    return ingress.model_copy(
        update={
            "semantic_egress_governance": AuthenticatedSemanticEgressGovernance(
                classification="internal",
                provider="capture",
                model="capture-v1",
                region="local",
                retention_mode="none",
                training_use=False,
            ),
            "semantic_source_authority": AuthenticatedSemanticSourceAuthority(
                authority_class="official",
                authenticated_provenance_class="host",
                governing_principal_id="principal:alice",
                policy_revision="trust-r1",
                provenance_digest="b" * 64,
            ),
            "semantic_source_interval": AuthenticatedSemanticSourceInterval(
                start=datetime(2026, 1, 1, tzinfo=UTC),
                end=datetime(2026, 2, 1, tzinfo=UTC),
                authority_basis="server_source_metadata",
                provenance_digest="c" * 64,
                policy_revision="trust-r1",
            ),
        }
    )


def test_server_governance_builder_is_deterministic_and_persisted_across_reload() -> None:
    text = "Atlas owner is Bob."
    ingress = _governed_ingress()
    event = ProviderEvent(event_id="event-1", operation=ProviderOperation.CHAT_USER_TURN, content=text)
    identity = DeliveryIdentity.create(ingress.delivery_principal_binding, event.event_id)
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    source_digest = step_one_source_digest(
        source_id=source_id, delivery_key_digest=identity.delivery_key_digest, original_text=text,
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    first = derive_source_governance_material(
        ingress=ingress, event=event, source_id=source_id, source_digest=source_digest,
        received_at=now, retained_at=now,
    )
    second = derive_source_governance_material(
        ingress=ingress, event=event, source_id=source_id, source_digest=source_digest,
        received_at=now, retained_at=now,
    )
    assert first.kind == second.kind == "governed"
    assert first.material == second.material
    assert first.material is not None
    request = SourceAdmissionRequest(
        delivery_identity=identity, delivery_key_digest=identity.delivery_key_digest,
        required_outcome_scopes=ingress.required_outcome_scopes,
        source_kind="conversation_turn", original_text=text,
    )
    record = build_admitted_source_record(
        request=request, source_id=source_id, retained_at=now,
        material=build_verbatim_step_one_material(
            source_id=source_id, source_digest=source_digest, original_text=text,
            required_outcome_scopes=first.material.required_outcome_scopes,
            semantic_context=first.material.semantic_context,
            segment_governance_carriers=first.material.segment_governance_carriers,
            message_admission_carriers=first.material.message_admission_carriers,
            governance_carrier_artifact=first.material.governance_carrier_artifact,
            admission_scope_authorization_proof=first.material.admission_scope_authorization_proof,
            source_reference=event.event_id,
        ),
    )
    reopened = source_observation_from_record(record.model_validate(record.model_dump(mode="json")))
    assert reopened.is_step_one_admitted
    assert reopened.governance_carrier_artifact == first.material.governance_carrier_artifact


def test_server_governance_builder_rejects_missing_or_substituted_host_authority() -> None:
    ingress = _governed_ingress()
    event = ProviderEvent(event_id="event-1", operation=ProviderOperation.CHAT_USER_TURN, content="Atlas owner is Bob.")
    identity = DeliveryIdentity.create(ingress.delivery_principal_binding, event.event_id)
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    source_digest = step_one_source_digest(
        source_id=source_id, delivery_key_digest=identity.delivery_key_digest, original_text=event.content or "",
    )
    now = datetime(2026, 1, 1, tzinfo=UTC)
    missing = derive_source_governance_material(
        ingress=ingress.model_copy(update={"semantic_source_authority": None}), event=event,
        source_id=source_id, source_digest=source_digest, received_at=now, retained_at=now,
    )
    assert missing.kind == "nonpromoting"
    assert missing.reason_codes == ("semantic_source_authority_unavailable",)
    substituted = derive_source_governance_material(
        ingress=ingress.model_copy(update={"semantic_source_interval": ingress.semantic_source_interval.model_copy(update={"policy_revision": "other"})}),
        event=event, source_id=source_id, source_digest=source_digest, received_at=now, retained_at=now,
    )
    assert substituted.kind == "nonpromoting"
    assert substituted.reason_codes == ("semantic_source_interval_policy_mismatch",)

    record, _, _, _ = _values()
    body = record.model_copy(deep=True)
    material = decode_typed_value(base64.b64decode(body.content["source_admission"]["step_one_material_ctv"]))
    material["governance_carrier_artifact"]["artifact_id"] = "substituted"
    body.content["source_admission"]["step_one_material_ctv"] = base64.b64encode(encode_typed_value(material)).decode("ascii")
    with pytest.raises(ValueError, match="invalid|substituted|mismatch"):
        source_observation_from_record(body)


def test_authenticated_snapshot_projects_each_declared_message_with_separator_proofs() -> None:
    contexts = tuple(
        GovernedMessageSemanticContext.create(
            message_id=f"message-{index}", source_reference=f"ref:{index}", effective_scope="session:one",
            authority_digest=f"{index + 1:x}" * 64, data_classification="internal",
            modality="assertion", remote_egress_eligible=True,
        )
        for index in range(3)
    )
    envelope = GovernedConversationSnapshotInput(
        kind="conversation_snapshot", schema_version=1, session_id="session:one",
        messages=tuple(
            ProviderEnvelopeMessage(message_id=f"message-{index}", sequence_number=index, role="user", content=text, source_reference=f"ref:{index}")
            for index, text in enumerate(("same", "middle", "same"))
        ), message_contexts=contexts, snapshot_source_reference="snapshot:one",
    )
    content = json.dumps(envelope.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    ingress = _governed_ingress().model_copy(update={
        "structured_source_envelope": AuthenticatedStructuredSourceEnvelope.create(
            event_id="snapshot-event", operation="session_end", canonical_envelope_json=content,
        )
    })
    event = ProviderEvent(event_id="snapshot-event", operation=ProviderOperation.SESSION_END, content=content)
    request = ProviderEventNormalizer(ingress).normalize(event)
    identity = request.delivery_identity
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    source_digest = step_one_source_digest(source_id=source_id, delivery_key_digest=identity.delivery_key_digest, original_text=content)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    governance = derive_source_governance_material(
        ingress=ingress, event=event, source_id=source_id, source_digest=source_digest, received_at=now, retained_at=now,
    )
    assert governance.kind == "governed" and governance.material is not None
    material = build_structured_step_one_material_from_governance(
        source_id=source_id, source_digest=source_digest, original_text=content,
        envelope=request.structured_source_envelope, governance=governance.material,
    )
    projection = material.semantic_text_projection
    assert projection.projection_text == "same\nmiddle\nsame"
    assert tuple(segment.projection_span.start for segment in projection.segments) == (0, 5, 12)
    assert tuple(segment.source_reference for segment in projection.segments) == ("ref:0", "ref:1", "ref:2")
    assert tuple(segment.message_semantic_context_digest for segment in projection.segments) == tuple(context.context_digest for context in contexts)
    assert tuple(segment.text_mapping_proof.canonical_json_pointer for segment in projection.segments) == ("/messages/0/content", "/messages/1/content", "/messages/2/content")
    assert projection.segments[0].segment_text_artifact != projection.segments[2].segment_text_artifact
    reopened = source_observation_from_record(
        build_admitted_source_record(
            request=request, source_id=source_id, retained_at=now, material=material, session_id="session:one",
        )
    )
    assert reopened.semantic_text_projection == projection

    with pytest.raises(ValueError, match="substituted"):
        ProviderEventNormalizer(ingress).normalize(event.model_copy(update={"content": content + " "}))
    with pytest.raises(ValueError, match="unavailable"):
        ProviderEventNormalizer(ingress.model_copy(update={"structured_source_envelope": None})).normalize(event)


def test_authenticated_delegation_projects_only_result_content() -> None:
    envelope = DelegationResultSourceEnvelope(
        kind="delegation_result", schema_version=1, task_id="task:one", result_id="result:one", result_status="ok",
        content="delegated fact", task_source_reference="task-ref", result_source_reference="result-ref",
    )
    content = json.dumps(envelope.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    ingress = _governed_ingress().model_copy(update={
        "structured_source_envelope": AuthenticatedStructuredSourceEnvelope.create(
            event_id="delegation-event", operation="delegation_result", canonical_envelope_json=content,
        )
    })
    event = ProviderEvent(event_id="delegation-event", operation=ProviderOperation.DELEGATION_RESULT, content=content)
    request = ProviderEventNormalizer(ingress).normalize(event)
    identity = request.delivery_identity
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    source_digest = step_one_source_digest(source_id=source_id, delivery_key_digest=identity.delivery_key_digest, original_text=content)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    governance = derive_source_governance_material(ingress=ingress, event=event, source_id=source_id, source_digest=source_digest, received_at=now, retained_at=now)
    assert governance.kind == "governed" and governance.material is not None
    material = build_structured_step_one_material_from_governance(source_id=source_id, source_digest=source_digest, original_text=content, envelope=request.structured_source_envelope, governance=governance.material)
    segment = material.semantic_text_projection.segments[0]
    assert material.semantic_text_projection.projection_text == "delegated fact"
    assert segment.source_variant == "delegation_result_content"
    assert segment.source_reference == "result-ref"
    assert segment.message_semantic_context_digest is None and segment.message_admission_identity is None
