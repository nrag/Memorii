"""Atomic admission of one completed Hermes user/assistant turn.

This is the production-shaped boundary between a host-completed turn and the
existing semantic-ingestion operation store.  It retains source evidence and
creates a fenced pending operation only; normalization and graph work
remain owned by later stages.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from memorii.core.memory_evolution.admission import (
    GovernedSourceAdmissionService,
    SourceAdmissionAccepted,
    source_admission_source_digest,
)
from memorii.core.memory_evolution.atomic_store import PreplanningPublication, SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    DeliveryIdentity,
    OperationFenceBinding,
    derive_composite_child_delivery_id,
    encode_typed_value,
)
from memorii.core.memory_evolution.source_admission import (
    ProviderEventNormalizer,
    SourceAdmissionRequest,
    build_admitted_source_record,
    build_step_one_material_from_governance,
    step_one_source_digest,
)
from memorii.core.memory_evolution.source_governance import (
    derive_source_governance_material,
)
from memorii.core.memory_evolution.writer_admission import SemanticWriterCommitBinding
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.core.semantic_ingestion.contracts import (
    AuthenticatedSourceIntervalEvidence,
    SourceAuthority,
    SourceAuthorityEvidence,
    TimeInterval,
)

_CHILD_KINDS = ("hermes-completed-turn-user", "hermes-completed-turn-assistant")
_DIGEST = r"^[0-9a-f]{64}$"


class HermesCompletedTurnMessage(BaseModel):
    """One exact message from the completed host turn."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class HermesCompletedTurnAdmissionRequest(BaseModel):
    """Authenticated host facts required to derive one durable turn identity."""

    installation_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    authenticated_author_id: str = Field(min_length=1)
    authenticated_agent_id: str = Field(min_length=1)
    project_task_namespace: str = Field(min_length=1)
    turn_ordinal: int = Field(ge=1)
    canonical_transcript_digest: str = Field(pattern=_DIGEST)
    completed_messages: tuple[HermesCompletedTurnMessage, HermesCompletedTurnMessage]
    completed_at: datetime
    ingress: AuthenticatedIngressContext

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    @model_validator(mode="after")
    def validate_completed_pair(self) -> HermesCompletedTurnAdmissionRequest:
        if tuple(message.role for message in self.completed_messages) != ("user", "assistant"):
            raise ValueError("completed Hermes turn must contain ordered user and assistant messages")
        if self.completed_at.tzinfo is None:
            raise ValueError("completed Hermes turn timestamp must be timezone-aware")
        if self.project_task_namespace.strip() != self.project_task_namespace:
            raise ValueError("project task namespace must be exact")
        return self

    @property
    def delivery_id(self) -> str:
        """Stable delivery ledger coordinate for one completed host turn.

        The canonical full-transcript digest is part of the host delivery
        coordinate. Exact replays therefore share a coordinate while equal
        final pairs at distinct transcript positions cannot collide.
        """

        payload = self.model_dump(
            mode="python",
            exclude={
                "ingress",
                "completed_at",
                "completed_messages",
            },
        )
        return (
            "hermes-completed-turn:v1:"
            + sha256(b"memorii.hermes.completed-turn.delivery.v1\0" + encode_typed_value(payload)).hexdigest()
        )

    @property
    def operation_id(self) -> str:
        return (
            "hermes-completed-turn-operation:v1:"
            + sha256(b"memorii.hermes.completed-turn.operation.v1\0" + self.delivery_id.encode("ascii")).hexdigest()
        )


class HermesCompletedTurnNormalizationInputs(BaseModel):
    """Typed handoff for the later dynamic normalization owner."""

    operation_fence: OperationFenceBinding
    source_ids: tuple[str, str]
    source_digests: tuple[str, str]
    child_delivery_ids: tuple[str, str]
    child_delivery_identities: tuple[DeliveryIdentity, DeliveryIdentity]
    project_task_namespace: str
    authenticated_ingress: AuthenticatedIngressContext
    source_admissions: tuple[SourceAdmissionAccepted, SourceAdmissionAccepted]

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_admission_evidence(self) -> HermesCompletedTurnNormalizationInputs:
        for source_id, source_digest, identity, admission in zip(
            self.source_ids,
            self.source_digests,
            self.child_delivery_identities,
            self.source_admissions,
            strict=True,
        ):
            if (
                admission.source_id != source_id
                or admission.source_digest != source_digest
                or admission.delivery_identity != identity
                or admission.operation_fence_binding.operation_id != self.operation_fence.operation_id
            ):
                raise ValueError("completed Hermes turn admission evidence is substituted")
        if (
            tuple(identity.normalized_delivery_id.value for identity in self.child_delivery_identities)
            != self.child_delivery_ids
        ):
            raise ValueError("completed Hermes turn child delivery coordinate is substituted")
        if self.source_admissions[0].operation_fence_binding != self.operation_fence:
            raise ValueError("completed Hermes turn operation fence does not own user admission")
        if any(
            identity.delivery_principal_binding_digest
            != self.authenticated_ingress.delivery_principal_binding.binding_digest
            for identity in self.child_delivery_identities
        ):
            raise ValueError("completed Hermes turn ingress evidence is substituted")
        return self


class HermesCompletedTurnAdmission(BaseModel):
    """Durable completed-turn admission result with a live pending operation."""

    publication: PreplanningPublication
    normalization_inputs: HermesCompletedTurnNormalizationInputs

    model_config = ConfigDict(extra="forbid", frozen=True)


class HermesCompletedTurnAdmissionService:
    """Create exactly one atomically-retained completed-turn operation."""

    def __init__(
        self,
        *,
        atomic_store: SemanticIngestionAtomicStore,
        writer_binding: SemanticWriterCommitBinding,
    ) -> None:
        self._atomic_store = atomic_store
        self._writer_binding = writer_binding

    def admit(self, request: HermesCompletedTurnAdmissionRequest) -> HermesCompletedTurnAdmission:
        """Publish both sources, their delivery ledgers, and one pending operation atomically."""

        principal = request.ingress.delivery_principal_binding
        parent_delivery = request.delivery_id
        child_delivery_ids = tuple(
            derive_composite_child_delivery_id(parent_delivery, child_kind) for child_kind in _CHILD_KINDS
        )
        child_identities = tuple(
            DeliveryIdentity.create(
                principal,
                child_delivery_id,
            )
            for child_delivery_id in child_delivery_ids
        )
        prepared = tuple(
            _prepare_governed_child_source(
                request=request,
                message=message,
                child_delivery_id=child_delivery_id,
                child_identity=identity,
                child_kind=child_kind,
            )
            for message, child_delivery_id, identity, child_kind in zip(
                request.completed_messages,
                child_delivery_ids,
                child_identities,
                _CHILD_KINDS,
                strict=True,
            )
        )
        self._reject_changed_delivery(tuple(item.source for item in prepared))
        admission_service = GovernedSourceAdmissionService(self._atomic_store._memory_plane)
        prepared_admissions = tuple(
            admission_service.prepare_atomic(
                source=item.source,
                delivery_identity=item.request.delivery_identity,
                ingress=request.ingress,
                operation_id=request.operation_id,
                outcome_kind="selected_pipeline_pending",
                normalized_input=item.event.content.encode("utf-8"),
                bootstrap_language_evidence=item.request.bootstrap_language_evidence,
            )
            for item in prepared
        )
        publication = self._atomic_store.admit_source_group(
            prepared_sources=prepared_admissions,
            pending_source_index=0,
            writer_binding=self._writer_binding,
        )
        return HermesCompletedTurnAdmission(
            publication=publication,
            normalization_inputs=HermesCompletedTurnNormalizationInputs(
                operation_fence=publication.operation.operation_fence,
                source_ids=(prepared_admissions[0].accepted.source_id, prepared_admissions[1].accepted.source_id),
                source_digests=(
                    prepared_admissions[0].accepted.source_digest,
                    prepared_admissions[1].accepted.source_digest,
                ),
                child_delivery_ids=(child_delivery_ids[0], child_delivery_ids[1]),
                child_delivery_identities=(child_identities[0], child_identities[1]),
                project_task_namespace=request.project_task_namespace,
                authenticated_ingress=request.ingress,
                source_admissions=(prepared_admissions[0].accepted, prepared_admissions[1].accepted),
            ),
        )

    def _reject_changed_delivery(self, sources: tuple[CanonicalMemoryRecord, ...]) -> None:
        """Fail closed when a host reuses an ordinal for changed turn bytes."""

        for source in sources:
            existing = self._atomic_store._memory_plane.get_record(source.memory_id)
            if existing is not None and (existing.text != source.text or existing.content != source.content):
                raise ValueError("completed Hermes turn delivery collides with different transcript")


class _PreparedGovernedChild:
    """The exact governed Step-1 material for one composite Hermes child."""

    def __init__(
        self,
        *,
        event: ProviderEvent,
        request: SourceAdmissionRequest,
        source: CanonicalMemoryRecord,
    ) -> None:
        self.event = event
        self.request = request
        self.source = source


def _prepare_governed_child_source(
    *,
    request: HermesCompletedTurnAdmissionRequest,
    message: HermesCompletedTurnMessage,
    child_delivery_id: str,
    child_identity: DeliveryIdentity,
    child_kind: str,
) -> _PreparedGovernedChild:
    """Build the canonical Step-1 child before constructing an operation fence.

    Composite delivery coordinates are internal, derived values.  The public
    ``ProviderEvent`` constructor rejects them, so this owner constructs a
    closed event only after checking the exact child coordinate and feeds it
    directly to the canonical normalizer.
    """

    expected_child_delivery_id = derive_composite_child_delivery_id(request.delivery_id, child_kind)
    if child_delivery_id != expected_child_delivery_id:
        raise ValueError("completed Hermes turn child delivery coordinate is invalid")
    operation = ProviderOperation.CHAT_USER_TURN if message.role == "user" else ProviderOperation.CHAT_ASSISTANT_TURN
    event = ProviderEvent.model_construct(
        event_id=child_delivery_id,
        operation=operation,
        content=message.content,
        role=message.role,
        session_id=request.session_id,
        task_id=request.project_task_namespace,
        user_id=request.authenticated_author_id,
        language=request.ingress.language_declaration or "und",
        timestamp=request.completed_at,
    )
    normalized = ProviderEventNormalizer(request.ingress).normalize(event)
    if normalized.delivery_identity != child_identity:
        raise ValueError("completed Hermes turn normalized delivery identity is substituted")
    source_id = "semantic_ingestion:source:" + normalized.delivery_key_digest
    source_digest = step_one_source_digest(
        source_id=source_id,
        delivery_key_digest=normalized.delivery_key_digest,
        original_text=normalized.original_text,
    )
    governance = derive_source_governance_material(
        ingress=request.ingress,
        event=event,
        source_id=source_id,
        source_digest=source_digest,
        received_at=request.completed_at,
        retained_at=request.completed_at,
    )
    if governance.kind != "governed" or governance.material is None:
        raise ValueError("completed Hermes turn source governance is unavailable")
    material = governance.material
    normalized = normalized.bind_bootstrap_language_evidence(
        ingress=request.ingress,
        source_id=source_id,
        source_digest=source_digest,
        segment_governance_set_digest=material.segment_governance_carriers.carrier_set_digest,
        governance_carrier_artifact_digest=material.governance_carrier_artifact.artifact_digest,
        segment_governance_carriers_digest=material.segment_governance_carriers.carrier_set_digest,
        message_admission_carriers_digest=material.message_admission_carriers.carrier_set_digest,
    )
    source = build_admitted_source_record(
        request=normalized,
        source_id=source_id,
        retained_at=request.completed_at,
        material=build_step_one_material_from_governance(
            source_id=source_id,
            source_digest=source_digest,
            original_text=normalized.original_text,
            source_reference=event.event_id,
            governance=material,
        ),
        session_id=request.session_id,
        task_id=request.project_task_namespace,
        user_id=request.authenticated_author_id,
        agent_id=request.authenticated_agent_id,
    )
    source = _retain_source_authority_evidence(
        source=source,
        source_id=source_id,
        source_digest=source_digest,
        ingress=request.ingress,
    )
    if source_admission_source_digest(source) != source_digest:
        raise ValueError("completed Hermes turn Step-1 source digest is substituted")
    return _PreparedGovernedChild(event=event, request=normalized, source=source)


def _retain_source_authority_evidence(
    *,
    source: CanonicalMemoryRecord,
    source_id: str,
    source_digest: str,
    ingress: AuthenticatedIngressContext,
) -> CanonicalMemoryRecord:
    """Seal the typed source authority needed to resume after process loss."""

    metadata = ingress.semantic_source_authority
    if metadata is None:
        raise ValueError("completed Hermes turn source authority is unavailable")
    authority = SourceAuthorityEvidence.create(
        source_id=source_id,
        source_digest=source_digest,
        authority=SourceAuthority(
            authority_class=metadata.authority_class,
            authenticated_provenance_class=metadata.authenticated_provenance_class,
            governing_principal_id=metadata.governing_principal_id,
            policy_revision=metadata.policy_revision,
        ),
        provenance_digest=metadata.provenance_digest,
    )
    interval_metadata = ingress.semantic_source_interval
    interval = None
    if interval_metadata is not None:
        if interval_metadata.policy_revision != metadata.policy_revision:
            raise ValueError("completed Hermes turn source interval policy is substituted")
        interval = AuthenticatedSourceIntervalEvidence.create(
            source_id=source_id,
            source_digest=source_digest,
            interval=TimeInterval(
                start=interval_metadata.start,
                end=interval_metadata.end,
            ),
            authority_basis=interval_metadata.authority_basis,
            provenance_digest=interval_metadata.provenance_digest,
            policy_revision=interval_metadata.policy_revision,
            source_authority_evidence_digest=authority.evidence_digest,
        )
    content = dict(source.content)
    admission = dict(content.get("source_admission", {}))
    admission["retained_source_authority_evidence"] = authority.model_dump(mode="json")
    admission["retained_source_interval_evidence"] = None if interval is None else interval.model_dump(mode="json")
    admission["retained_authenticated_ingress"] = ingress.model_dump(mode="json")
    content["source_admission"] = admission
    return source.model_copy(update={"content": content})


def canonical_transcript_digest(
    messages: tuple[HermesCompletedTurnMessage, HermesCompletedTurnMessage],
) -> str:
    """Digest the exact ordered host pair before it reaches the delivery ledger."""

    return sha256(
        b"memorii.hermes.completed-turn.transcript.v1\0"
        + encode_typed_value(tuple(message.model_dump(mode="python") for message in messages))
    ).hexdigest()


__all__ = [
    "HermesCompletedTurnAdmission",
    "HermesCompletedTurnAdmissionRequest",
    "HermesCompletedTurnAdmissionService",
    "HermesCompletedTurnMessage",
    "HermesCompletedTurnNormalizationInputs",
    "canonical_transcript_digest",
]
