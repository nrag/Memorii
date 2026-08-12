"""Canonical Step-1 request boundary and closed provider-operation mapping.

The historical admission service remains the persistence implementation while
its durable record migration is in progress.  New callers normalize a provider
event here instead of deriving source identity or operation semantics locally.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapAdmissionPin,
    BootstrapAuthenticatedLanguageEvidence,
    GovernedSourceAdmissionFact,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import SourceObservation
from memorii.core.memory_evolution.source_governance import require_complete_scope_authorization
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderEvent
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility, SourceModality

SourceKind = Literal[
    "conversation_turn", "conversation_snapshot", "explicit_memory_write", "delegation_result"
]

if TYPE_CHECKING:
    pass


def _canonical_json(value: object) -> str:
    """The closed envelope profile used for retained structured source text."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ProviderEnvelopeMessage(BaseModel):
    message_id: str = Field(min_length=1)
    sequence_number: int = Field(ge=0)
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class GovernedMessageSemanticContext(BaseModel):
    """Authenticated semantic context retained only inside a snapshot envelope."""

    message_id: str = Field(min_length=1)
    source_reference: str = Field(min_length=1)
    effective_scope: str = Field(min_length=1)
    authority_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    data_classification: str = Field(min_length=1)
    modality: str = Field(min_length=1)
    remote_egress_eligible: bool
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_context(self) -> GovernedMessageSemanticContext:
        body = self.model_dump(mode="python", exclude={"context_digest"})
        expected = sha256(
            b"memorii.semantic-ingestion.governed-message-semantic-context.v1\0" + encode_typed_value(body)
        ).hexdigest()
        if self.context_digest != expected:
            raise ValueError("governed message semantic context digest mismatch")
        return self

    @classmethod
    def create(cls, **body: object) -> GovernedMessageSemanticContext:
        return cls(
            **body,
            context_digest=sha256(
                b"memorii.semantic-ingestion.governed-message-semantic-context.v1\0" + encode_typed_value(body)
            ).hexdigest(),
        )


class GovernedConversationSnapshotInput(BaseModel):
    kind: Literal["conversation_snapshot"]
    schema_version: Literal[1]
    session_id: str = Field(min_length=1)
    messages: tuple[ProviderEnvelopeMessage, ...] = Field(min_length=1)
    message_contexts: tuple[GovernedMessageSemanticContext, ...] = Field(min_length=1)
    snapshot_source_reference: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_snapshot(self) -> GovernedConversationSnapshotInput:
        keys = tuple((message.message_id, message.source_reference) for message in self.messages)
        if len(set(keys)) != len(keys) or tuple(message.sequence_number for message in self.messages) != tuple(range(len(self.messages))):
            raise ValueError("governed snapshot messages must be unique and contiguous")
        context_keys = tuple((context.message_id, context.source_reference) for context in self.message_contexts)
        if context_keys != keys:
            raise ValueError("governed snapshot contexts must be an ordered message bijection")
        return self


class DelegationResultSourceEnvelope(BaseModel):
    kind: Literal["delegation_result"]
    schema_version: Literal[1]
    task_id: str = Field(min_length=1)
    result_id: str = Field(min_length=1)
    result_status: str = Field(min_length=1)
    content: str = Field(min_length=1)
    task_source_reference: str = Field(min_length=1)
    result_source_reference: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_delegation(self) -> DelegationResultSourceEnvelope:
        if self.task_id == self.result_id or self.task_source_reference == self.result_source_reference:
            raise ValueError("delegation task and result identities must be distinct")
        return self


ProviderSourceEnvelope = GovernedConversationSnapshotInput | DelegationResultSourceEnvelope


class StepOneAdmissionMaterial(BaseModel):
    """Complete server-derived authority retained with one source record.

    Public provider metadata cannot populate this value.  A later provider
    composition route supplies authenticated ingress and policy output.
    """

    required_outcome_scopes: object
    semantic_context: object
    semantic_text_projection: object
    segment_governance_carriers: object
    message_admission_carriers: object
    governance_carrier_artifact: object
    admission_scope_authorization_proof: object

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class SourceAdmissionRequest(BaseModel):
    """Complete server-normalized input to immutable source retention."""

    delivery_identity: DeliveryIdentity
    delivery_key_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    required_outcome_scopes: RequiredOutcomeScopeSet
    source_kind: SourceKind
    # Semantic projection is defined over nonempty source spans.  Empty host
    # events are evidence-only at the coordinator boundary and must never be
    # representable as an admission request.
    original_text: str = Field(min_length=1)
    structured_source_envelope: ProviderSourceEnvelope | None = None
    declared_language: str | None = None
    bootstrap_language_evidence: BootstrapAuthenticatedLanguageEvidence | None = None

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_delivery(self) -> SourceAdmissionRequest:
        if self.delivery_key_digest != self.delivery_identity.delivery_key_digest:
            raise ValueError("source admission delivery key is substituted")
        if self.source_kind in {"conversation_snapshot", "delegation_result"} and self.structured_source_envelope is None:
            raise ValueError("structured source admission requires an authenticated envelope")
        if self.source_kind not in {"conversation_snapshot", "delegation_result"} and self.structured_source_envelope is not None:
            raise ValueError("verbatim source admission cannot retain a structured envelope")
        return self

    def bind_bootstrap_language_evidence(
        self,
        *,
        ingress: AuthenticatedIngressContext,
        source_id: str,
        source_digest: str,
        segment_governance_set_digest: str,
        governance_carrier_artifact_digest: str,
        segment_governance_carriers_digest: str,
        message_admission_carriers_digest: str,
    ) -> SourceAdmissionRequest:
        """Bind sealed retained/governance authority after Step-1 retention."""
        if self.delivery_identity.delivery_principal_binding_digest != ingress.delivery_principal_binding.binding_digest:
            raise ValueError("bootstrap language evidence ingress is substituted")
        return self.model_copy(update={
            "bootstrap_language_evidence": derive_bootstrap_authenticated_language_evidence(
                ingress=ingress, source_id=source_id, source_digest=source_digest,
                original_text=self.original_text,
                segment_governance_set_digest=segment_governance_set_digest,
                governance_carrier_artifact_digest=governance_carrier_artifact_digest,
                segment_governance_carriers_digest=segment_governance_carriers_digest,
                message_admission_carriers_digest=message_admission_carriers_digest,
            )
        })


class DeliveryAuthorizationRequest(BaseModel):
    """Ephemeral current-session check used only at CAS linearization points."""

    delivery_identity: DeliveryIdentity
    ingress: AuthenticatedIngressContext

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_owner(self) -> DeliveryAuthorizationRequest:
        if self.delivery_identity.delivery_principal_binding_digest != self.ingress.delivery_principal_binding.binding_digest:
            raise ValueError("delivery authorization principal is substituted")
        require_complete_scope_authorization(
            ingress=self.ingress, required_outcome_scopes=self.ingress.required_outcome_scopes
        )
        return self


class BootstrapPreparedSourceAccepted(BaseModel):
    """The only bootstrap result permitted before writer handoff."""

    kind: Literal["bootstrap_prepared_source_accepted"] = "bootstrap_prepared_source_accepted"
    observation: SourceObservation
    source_admission: GovernedSourceAdmissionFact
    bootstrap_language_evidence: BootstrapAuthenticatedLanguageEvidence
    delivery_identity: DeliveryIdentity
    operation_fence_binding: OperationFenceBinding
    authority_pin: BootstrapAdmissionPin
    prepared_generation: int = Field(ge=1)
    prepared_source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_result(self) -> BootstrapPreparedSourceAccepted:
        body = self.model_dump(mode="python", exclude={"result_digest"})
        if self.result_digest != sha256(
            b"memorii.semantic_ingestion.bootstrap_prepared_source_accepted.v1\0" + encode_typed_value(body)
        ).hexdigest():
            raise ValueError("bootstrap prepared source result digest mismatch")
        return self


def derive_bootstrap_authenticated_language_evidence(
    *,
    ingress: AuthenticatedIngressContext,
    source_id: str,
    source_digest: str,
    original_text: str,
    segment_governance_set_digest: str,
    governance_carrier_artifact_digest: str,
    segment_governance_carriers_digest: str,
    message_admission_carriers_digest: str,
) -> BootstrapAuthenticatedLanguageEvidence:
    """Derive the only bootstrap language authority from sealed host facts.

    Callers supply digests of the already sealed governance carriers rather
    than carrier objects, so this boundary cannot invent or select governance.
    """
    return BootstrapAuthenticatedLanguageEvidence.create(
        source_id=source_id,
        source_digest=source_digest,
        original_text_digest=sha256(original_text.encode("utf-8")).hexdigest(),
        delivery_principal_binding_digest=ingress.delivery_principal_binding.binding_digest,
        segment_governance_set_digest=segment_governance_set_digest,
        governance_carrier_artifact_digest=governance_carrier_artifact_digest,
        segment_governance_carriers_digest=segment_governance_carriers_digest,
        message_admission_carriers_digest=message_admission_carriers_digest,
        language_declaration=ingress.language_declaration,
        language_evidence_kind=ingress.language_evidence_kind,
        language_evidence_trust=ingress.language_evidence_trust,
        language_governance_agreement=ingress.language_governance_agreement,
    )


@dataclass(frozen=True)
class ProviderEventNormalizer:
    """Closed operation mapper; unknown operations never become retained input."""

    ingress: AuthenticatedIngressContext

    _MAPPING = {
        "chat_user_turn": "conversation_turn",
        "chat_assistant_turn": "conversation_turn",
        "session_end": "conversation_snapshot",
        "pre_compress": "conversation_snapshot",
        "memory_write_longterm": "explicit_memory_write",
        "memory_write_user": "explicit_memory_write",
        "memory_write_dailylog": "explicit_memory_write",
        "delegation_result": "delegation_result",
    }

    def normalize(self, event: ProviderEvent) -> SourceAdmissionRequest:
        source_kind = self._MAPPING.get(event.operation.value)
        if source_kind is None:
            raise ValueError("provider operation is not admitted for semantic ingestion")
        if event.content is None:
            raise ValueError("provider operation requires content")
        require_complete_scope_authorization(
            ingress=self.ingress,
            required_outcome_scopes=self.ingress.required_outcome_scopes,
        )
        identity = DeliveryIdentity.create(
            self.ingress.delivery_principal_binding, event.event_id
        )
        envelope = self._structured_envelope(event, source_kind)
        return SourceAdmissionRequest(
            delivery_identity=identity,
            delivery_key_digest=identity.delivery_key_digest,
            required_outcome_scopes=self.ingress.required_outcome_scopes,
            source_kind=source_kind,
            original_text=event.content,
            structured_source_envelope=envelope,
        )

    def _structured_envelope(self, event: ProviderEvent, source_kind: SourceKind) -> ProviderSourceEnvelope | None:
        if source_kind not in {"conversation_snapshot", "delegation_result"}:
            return None
        carrier = self.ingress.structured_source_envelope
        if carrier is None:
            raise ValueError("authenticated structured envelope unavailable")
        if carrier.event_id != event.event_id or carrier.operation != event.operation.value:
            raise ValueError("authenticated structured envelope is not bound to this provider event")
        if carrier.canonical_envelope_json != event.content:
            raise ValueError("provider event structured envelope bytes are substituted")
        try:
            parsed = json.loads(carrier.canonical_envelope_json)
        except json.JSONDecodeError as exc:
            raise ValueError("authenticated structured envelope is invalid JSON") from exc
        if _canonical_json(parsed) != carrier.canonical_envelope_json:
            raise ValueError("authenticated structured envelope is not canonical")
        if not isinstance(parsed, dict):
            raise ValueError("authenticated structured envelope must be an object")
        try:
            if source_kind == "conversation_snapshot":
                return GovernedConversationSnapshotInput.model_validate(parsed, strict=False)
            return DelegationResultSourceEnvelope.model_validate(parsed, strict=False)
        except ValueError as exc:
            raise ValueError("authenticated structured envelope is invalid") from exc


def build_verbatim_step_one_material(
    *,
    source_id: str,
    source_digest: str,
    original_text: str,
    required_outcome_scopes: object,
    semantic_context: object,
    segment_governance_carriers: object,
    message_admission_carriers: object,
    governance_carrier_artifact: object,
    admission_scope_authorization_proof: object,
    source_reference: str | None = None,
) -> StepOneAdmissionMaterial:
    """Derive the one-segment verbatim projection without semantic inference.

    The only transformed values are artifact IDs, digests, and byte-for-byte
    coordinate proofs.  Governance and semantic context are authenticated
    server inputs and are checked for exact source/carrier substitution.
    """
    from memorii.core.memory_evolution.source_governance import AdmissionScopeAuthorizationProof
    from memorii.core.semantic_ingestion.contracts import (
        GovernanceCarrierArtifact,
        MessageAdmissionCarrierSet,
        ProjectionTextSpan,
        RetainedSourceTextArtifact,
        RetainedSourceTextSpan,
        SegmentGovernanceCarrierSet,
        SegmentLocalTextArtifact,
        SegmentLocalTextSpan,
        SemanticProjectionSegment,
        SemanticProjectionTextArtifact,
        SourceSemanticContext,
        SourceSemanticTextProjection,
        VerbatimTextArtifactMappingProof,
    )
    from memorii.core.semantic_ingestion.contracts import (
        RequiredOutcomeScopeSet as SemanticRequiredOutcomeScopeSet,
    )

    if not isinstance(required_outcome_scopes, SemanticRequiredOutcomeScopeSet):
        raise ValueError("Step-1 requires server-derived semantic outcome scopes")
    if not isinstance(semantic_context, SourceSemanticContext):
        raise ValueError("Step-1 requires a server-derived semantic context")
    if not isinstance(segment_governance_carriers, SegmentGovernanceCarrierSet):
        raise ValueError("Step-1 requires complete segment governance")
    if not isinstance(message_admission_carriers, MessageAdmissionCarrierSet):
        raise ValueError("Step-1 requires complete message admission carriers")
    if not isinstance(governance_carrier_artifact, GovernanceCarrierArtifact):
        raise ValueError("Step-1 requires a governance carrier artifact")
    if not isinstance(admission_scope_authorization_proof, AdmissionScopeAuthorizationProof):
        raise ValueError("Step-1 requires an admission scope authorization proof")
    if semantic_context.source_id != source_id or semantic_context.source_digest != source_digest:
        raise ValueError("Step-1 semantic context is substituted")
    if (
        segment_governance_carriers.source_id != source_id
        or message_admission_carriers.source_id != source_id
        or governance_carrier_artifact.segment_governance != segment_governance_carriers
        or governance_carrier_artifact.message_admissions != message_admission_carriers
        or governance_carrier_artifact.required_outcome_scopes != required_outcome_scopes
    ):
        raise ValueError("Step-1 governance carriers are substituted")
    if len(segment_governance_carriers.bindings) != 1 or len(message_admission_carriers.identities) != 1:
        raise ValueError("verbatim Step-1 projection requires exactly one governed segment")

    text_digest = sha256(original_text.encode("utf-8")).hexdigest()
    token = sha256(f"{source_id}\0{text_digest}".encode()).hexdigest()
    retained = RetainedSourceTextArtifact.create(
        artifact_id=f"semantic_ingestion:retained:{token}", content_digest=text_digest,
        unicode_scalar_length=len(original_text),
    )
    projection = SemanticProjectionTextArtifact.create(
        artifact_id=f"semantic_ingestion:projection:{token}", content_digest=text_digest,
        unicode_scalar_length=len(original_text),
    )
    segment_id = segment_governance_carriers.bindings[0].segment_id
    local = SegmentLocalTextArtifact.create(
        artifact_id=f"semantic_ingestion:segment:{token}", projection_segment_id=segment_id,
        content_digest=text_digest, unicode_scalar_length=len(original_text),
    )
    retained_span = RetainedSourceTextSpan.create(
        artifact=retained, start=0, end=len(original_text), substring_digest=text_digest,
    )
    projection_span = ProjectionTextSpan.create(
        artifact=projection, start=0, end=len(original_text), substring_digest=text_digest,
    )
    local_span = SegmentLocalTextSpan.create(
        artifact=local, start=0, end=len(original_text), substring_digest=text_digest,
    )
    proof = VerbatimTextArtifactMappingProof.create(
        retained_span=retained_span, projection_span=projection_span, segment_span=local_span,
    )
    segment = SemanticProjectionSegment.create(
        segment_id=segment_id, projection_span=projection_span, segment_text_artifact=local,
        text_mapping_proof=proof, semantic_text=original_text, source_variant="verbatim_text",
        source_reference=source_reference,
        message_semantic_context_digest=segment_governance_carriers.bindings[0].message_semantic_context_digest,
        segment_governance=segment_governance_carriers.bindings[0],
        message_admission_identity=message_admission_carriers.identities[0],
    )
    projection_value = SourceSemanticTextProjection(
        schema_version=1, retained_source_digest=source_digest, retained_text_artifact=retained,
        required_outcome_scopes=required_outcome_scopes, projection_text_artifact=projection,
        projection_text=original_text, separator="\n", segments=(segment,),
        segment_governance_carriers=segment_governance_carriers,
        message_admission_carriers=message_admission_carriers, envelope_manifest_digest=None,
        projection_digest=projection.artifact_digest,
    )
    return StepOneAdmissionMaterial(
        required_outcome_scopes=required_outcome_scopes, semantic_context=semantic_context,
        semantic_text_projection=projection_value, segment_governance_carriers=segment_governance_carriers,
        message_admission_carriers=message_admission_carriers,
        governance_carrier_artifact=governance_carrier_artifact,
        admission_scope_authorization_proof=admission_scope_authorization_proof,
    )


def build_step_one_material_from_governance(
    *,
    source_id: str,
    source_digest: str,
    original_text: str,
    source_reference: str,
    governance: object,
) -> StepOneAdmissionMaterial:
    """Adapt the sole server-owned governance derivation to retained bytes."""
    from memorii.core.memory_evolution.source_governance import DerivedSourceGovernanceMaterial

    if not isinstance(governance, DerivedSourceGovernanceMaterial):
        raise ValueError("Step-1 requires governed source material")
    return build_verbatim_step_one_material(
        source_id=source_id,
        source_digest=source_digest,
        original_text=original_text,
        required_outcome_scopes=governance.required_outcome_scopes,
        semantic_context=governance.semantic_context,
        segment_governance_carriers=governance.segment_governance_carriers,
        message_admission_carriers=governance.message_admission_carriers,
        governance_carrier_artifact=governance.governance_carrier_artifact,
        admission_scope_authorization_proof=governance.admission_scope_authorization_proof,
        source_reference=source_reference,
    )


def build_structured_step_one_material_from_governance(
    *,
    source_id: str,
    source_digest: str,
    original_text: str,
    envelope: ProviderSourceEnvelope,
    governance: object,
) -> StepOneAdmissionMaterial:
    """Project only authenticated structured content into ordered source text.

    Boundaries originate in the closed retained envelope.  Neither public
    metadata nor text separators participate in selecting a segment.
    """
    from memorii.core.memory_evolution.source_governance import DerivedSourceGovernanceMaterial
    from memorii.core.semantic_ingestion.contracts import (
        EnvelopeFieldTextArtifactMappingProof,
        GovernanceCarrierArtifact,
        MessageAdmissionCarrierSet,
        MessageAdmissionIdentity,
        ProjectionTextSpan,
        RetainedSourceTextArtifact,
        SegmentGovernanceBinding,
        SegmentGovernanceCarrierSet,
        SegmentLocalTextArtifact,
        SegmentLocalTextSpan,
        SemanticProjectionSegment,
        SemanticProjectionTextArtifact,
        SourceSemanticTextProjection,
        contract_digest,
    )
    if not isinstance(governance, DerivedSourceGovernanceMaterial):
        raise ValueError("Step-1 requires governed source material")
    if _canonical_json(envelope.model_dump(mode="json")) != original_text:
        raise ValueError("structured Step-1 envelope bytes are substituted")
    if isinstance(envelope, GovernedConversationSnapshotInput):
        items = tuple(zip(envelope.messages, envelope.message_contexts, strict=True))
        variant = "conversation_message"
    else:
        items = ((
            ProviderEnvelopeMessage(message_id=envelope.result_id, sequence_number=0, role="delegation_result", content=envelope.content, source_reference=envelope.result_source_reference),
            None,
        ),)
        variant = "delegation_result_content"
    retained_digest = sha256(original_text.encode("utf-8")).hexdigest()
    token = sha256(f"{source_id}\0{retained_digest}".encode()).hexdigest()
    retained = RetainedSourceTextArtifact.create(
        artifact_id=f"semantic_ingestion:retained:{token}", content_digest=retained_digest,
        unicode_scalar_length=len(original_text),
    )
    texts = tuple(message.content for message, _ in items)
    projection_text = "\n".join(texts)
    projection_digest = sha256(projection_text.encode("utf-8")).hexdigest()
    projection = SemanticProjectionTextArtifact.create(
        artifact_id=f"semantic_ingestion:projection:{token}", content_digest=projection_digest,
        unicode_scalar_length=len(projection_text),
    )
    bindings: list[SegmentGovernanceBinding] = []
    admissions: list[MessageAdmissionIdentity] = []
    segment_values: list[SemanticProjectionSegment] = []
    offset = 0
    for index, (message, context) in enumerate(items):
        segment_id = f"semantic_ingestion:segment:{sha256(encode_typed_value((source_id, message.message_id, message.source_reference))).hexdigest()}"
        text_digest = sha256(message.content.encode("utf-8")).hexdigest()
        if context is None:
            context_digest = None
            authority_digest = contract_digest(b"memorii.semantic-ingestion.delegation-result-authority.v1", {"task_id": envelope.task_id, "result_id": envelope.result_id, "reference": message.source_reference})
            classification = "authenticated_delegation_result"
            modality = SourceModality.TOOL_RESULT
            egress = "allow_verbatim"
        else:
            context_digest = context.context_digest
            authority_digest = context.authority_digest
            classification = context.data_classification
            try:
                modality = SourceModality(context.modality)
            except ValueError as exc:
                raise ValueError("governed message context has unsupported modality") from exc
            egress = "allow_verbatim" if context.remote_egress_eligible else "deny"
        binding = SegmentGovernanceBinding.create(
            source_id=source_id, segment_id=segment_id,
            message_semantic_context_digest=context_digest or governance.semantic_context.context_digest,
            effective_scope_digest=governance.required_outcome_scopes.required_scope_set_digest,
            authority_digest=authority_digest, data_classification=classification, modality=modality,
            provider_egress_decision_digest=contract_digest(
                b"memorii.semantic-ingestion.structured-segment-egress-decision.v1",
                {"source_id": source_id, "segment_id": segment_id, "context_digest": context_digest, "disposition": egress},
            ), egress_disposition=egress,
        )
        local = SegmentLocalTextArtifact.create(
            artifact_id=f"semantic_ingestion:segment:{token}:{index}", projection_segment_id=segment_id,
            content_digest=text_digest, unicode_scalar_length=len(message.content),
        )
        projection_span = ProjectionTextSpan.create(artifact=projection, start=offset, end=offset + len(message.content), substring_digest=text_digest)
        local_span = SegmentLocalTextSpan.create(artifact=local, start=0, end=len(message.content), substring_digest=text_digest)
        pointer = f"/messages/{index}/content" if isinstance(envelope, GovernedConversationSnapshotInput) else "/content"
        encoded_value = _canonical_json(message.content).encode("utf-8")
        proof = EnvelopeFieldTextArtifactMappingProof.create(
            retained_artifact=retained, canonical_json_pointer=pointer,
            canonical_encoded_field_value_bytes=encoded_value,
            canonical_encoded_field_value_digest=sha256(encoded_value).hexdigest(),
            decoded_content_bytes=message.content.encode("utf-8"), decoded_content_text_digest=text_digest,
            projection_segment_id=segment_id, projection_span=projection_span, segment_artifact=local,
            segment_span=local_span,
        )
        admission = None
        if context is not None:
            admission = MessageAdmissionIdentity.create(
                delivery_principal_binding_digest=governance.admission_scope_authorization_proof.delivery_principal_binding_digest,
                authenticated_source_reference=message.source_reference,
                authenticated_source_reference_key_digest=contract_digest(b"memorii.semantic-ingestion.authenticated-source-reference.v1", message.source_reference),
                message_bytes_digest=text_digest, segment_governance_binding_digest=binding.binding_digest,
            )
            admissions.append(admission)
        bindings.append(binding)
        segment_values.append(SemanticProjectionSegment.create(
            segment_id=segment_id, projection_span=projection_span, segment_text_artifact=local,
            text_mapping_proof=proof, semantic_text=message.content, source_variant=variant,
            source_reference=message.source_reference, message_semantic_context_digest=context_digest,
            segment_governance=binding, message_admission_identity=admission,
        ))
        offset = projection_span.end + (1 if index + 1 < len(items) else 0)
    carriers = SegmentGovernanceCarrierSet.create(source_id=source_id, bindings=tuple(bindings))
    admission_carriers = MessageAdmissionCarrierSet.create(source_id=source_id, identities=tuple(admissions))
    artifact = GovernanceCarrierArtifact.create(
        artifact_id=f"semantic_ingestion:governance:{source_digest}", atomic_generation=1,
        segment_governance=carriers, message_admissions=admission_carriers,
        required_outcome_scopes=governance.required_outcome_scopes,
    )
    return StepOneAdmissionMaterial(
        required_outcome_scopes=governance.required_outcome_scopes, semantic_context=governance.semantic_context,
        semantic_text_projection=SourceSemanticTextProjection(
            schema_version=1, retained_source_digest=source_digest, retained_text_artifact=retained,
            required_outcome_scopes=governance.required_outcome_scopes, projection_text_artifact=projection,
            projection_text=projection_text, separator="\n", segments=tuple(segment_values),
            segment_governance_carriers=carriers, message_admission_carriers=admission_carriers,
            envelope_manifest_digest=None, projection_digest=projection.artifact_digest,
        ), segment_governance_carriers=carriers, message_admission_carriers=admission_carriers,
        governance_carrier_artifact=artifact,
        admission_scope_authorization_proof=governance.admission_scope_authorization_proof,
    )


def build_admitted_source_record(
    *,
    request: SourceAdmissionRequest,
    source_id: str,
    retained_at: object,
    material: StepOneAdmissionMaterial,
    session_id: str | None = None,
    task_id: str | None = None,
    user_id: str | None = None,
) -> CanonicalMemoryRecord:
    """Create the exact raw record which atomic admission publishes verbatim."""
    if not isinstance(retained_at, datetime):
        raise TypeError("retained_at must be a server datetime")
    if retained_at.utcoffset() is None:
        raise ValueError("retained_at must be timezone-aware")
    content = {
        "text": request.original_text,
        "source_admission": {
            "delivery_identity": request.delivery_identity.model_dump(mode="json"),
            "delivery_key_digest": request.delivery_key_digest,
            "source_kind": request.source_kind,
            "declared_language": request.declared_language,
            "bootstrap_language_evidence": (
                None if request.bootstrap_language_evidence is None
                else request.bootstrap_language_evidence.model_dump(mode="json")
            ),
            # Store CTV rather than JSON so tuples and immutable contracts
            # round-trip without loosening the strict persisted schemas.
            "step_one_material_ctv": base64.b64encode(
                encode_typed_value(material.model_dump(mode="python"))
            ).decode("ascii"),
        },
    }
    return CanonicalMemoryRecord(
        memory_id=source_id, domain=MemoryDomain.TRANSCRIPT, text=request.original_text, content=content,
        status=CommitStatus.COMMITTED, source_kind="semantic_ingestion_source", timestamp=retained_at,
        session_id=session_id, task_id=task_id, user_id=user_id, language=request.declared_language or "und",
        is_raw_event=True, visibility=MemoryRecordVisibility.INTERNAL_CONTROL,
    )


def step_one_source_digest(*, source_id: str, delivery_key_digest: str, original_text: str) -> str:
    """Stable retained-source identity, independent of derived projection bytes."""

    return sha256(
        b"memorii.semantic-ingestion.step-one-source.v1\0"
        + encode_typed_value({
            "source_id": source_id,
            "delivery_key_digest": delivery_key_digest,
            "original_text": original_text,
        })
    ).hexdigest()


__all__ = [
    "BootstrapAuthenticatedLanguageEvidence",
    "DeliveryAuthorizationRequest",
    "ProviderEventNormalizer",
    "SourceAdmissionRequest",
    "SourceKind",
    "StepOneAdmissionMaterial",
    "build_admitted_source_record",
    "build_step_one_material_from_governance",
    "build_structured_step_one_material_from_governance",
    "build_verbatim_step_one_material",
    "step_one_source_digest",
    "derive_bootstrap_authenticated_language_evidence",
    "DelegationResultSourceEnvelope",
    "GovernedConversationSnapshotInput",
    "GovernedMessageSemanticContext",
    "ProviderEnvelopeMessage",
    "ProviderSourceEnvelope",
]
