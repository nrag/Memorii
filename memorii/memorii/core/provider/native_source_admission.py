"""Retain trusted native user messages through the provider's Step-1 owner."""

from collections.abc import Callable
from datetime import UTC, datetime

from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, source_admission_source_digest
from memorii.core.memory_evolution.atomic_store import PreplanningStoreError, SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext, OperationFenceBinding
from memorii.core.memory_evolution.source_admission import (
    ProviderEventNormalizer,
    build_admitted_source_record,
    build_step_one_material_from_governance,
    step_one_source_digest,
)
from memorii.core.memory_evolution.source_governance import derive_source_governance_material
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.persistence.factory import PublishedMemoryPlaneStore
from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.core.semantic_ingestion.contracts import (
    GovernanceCarrierArtifact,
    MessageAdmissionCarrierSet,
    SegmentGovernanceCarrierSet,
)
from memorii.core.semantic_ingestion.source_authority_retention import retain_source_authority_evidence
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import StorageAdministrationService


class NativeSourceDeliveryConflict(ValueError):
    """A native delivery ID already owns different retained evidence."""


def retain_native_source(
    administration: StorageAdministrationService,
    *,
    event: ProviderEvent,
    ingress: AuthenticatedIngressContext,
    check_current: Callable[[], None],
) -> CanonicalMemoryRecord:
    """Retain one authorized delivery without starting extraction or graph work.

    The host owner supplies a live enrollment and task check scoped to this
    event and ingress. Its partition read runs before the write transaction
    under the same publication fence. It must not reacquire that fence.
    """
    principal = ingress.delivery_principal_binding.principal_subject_id
    authority = ingress.semantic_source_authority
    session_id, task_id = event.session_id, event.task_id
    if (
        event.operation != ProviderOperation.CHAT_USER_TURN
        or event.role != "user"
        or not event.content
        or not event.content.strip()
        or not session_id
        or not task_id
        or event.user_id != principal
        or authority is None
        or authority.authenticated_provenance_class != "authenticated_user"
    ):
        raise ValueError("native source requires an authenticated user turn with a session and task")

    normalized = ProviderEventNormalizer(ingress).normalize(event)
    identity = normalized.delivery_identity
    source_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
    source_digest = step_one_source_digest(
        source_id=source_id,
        delivery_key_digest=identity.delivery_key_digest,
        original_text=normalized.original_text,
    )
    fence = OperationFenceBinding.create(
        operation_id=event.event_id, source_id=source_id, source_digest=source_digest, delivery_identity=identity,
    )
    revoked = RefreshingRevokedIdentityView(administration.installation_root / "control")

    def verify_authority() -> None:
        check_current()
        if revoked.is_revoked_task(task_id) or revoked.is_revoked_source(source_id) or revoked.is_revoked_record(source_id):
            raise ValueError("native source is suppressed")

    plane = MemoryPlaneService(record_store=PublishedMemoryPlaneStore(
        administration, administration.memory_plane_store(), validate_authority=verify_authority,
    ))
    admissions = GovernedSourceAdmissionService(plane)

    def build_source(retained_at: datetime) -> CanonicalMemoryRecord:
        governance = derive_source_governance_material(
            ingress=ingress, event=event, source_id=source_id, source_digest=source_digest,
            received_at=retained_at, retained_at=retained_at,
        ).material
        if governance is None:
            raise ValueError("native source governance is unavailable")
        segments = governance.segment_governance_carriers
        messages = governance.message_admission_carriers
        artifact = governance.governance_carrier_artifact
        if not (
            isinstance(segments, SegmentGovernanceCarrierSet)
            and isinstance(messages, MessageAdmissionCarrierSet)
            and isinstance(artifact, GovernanceCarrierArtifact)
        ):
            raise ValueError("native source governance material is invalid")
        request = normalized.bind_bootstrap_language_evidence(
            ingress=ingress,
            source_id=source_id,
            source_digest=source_digest,
            segment_governance_set_digest=segments.carrier_set_digest,
            governance_carrier_artifact_digest=artifact.artifact_digest,
            segment_governance_carriers_digest=segments.carrier_set_digest,
            message_admission_carriers_digest=messages.carrier_set_digest,
        )
        source = build_admitted_source_record(
            request=request, source_id=source_id, retained_at=retained_at,
            material=build_step_one_material_from_governance(
                source_id=source_id, source_digest=source_digest, original_text=request.original_text,
                source_reference=event.event_id, governance=governance,
            ),
            session_id=session_id, task_id=task_id, user_id=principal,
            agent_id=ingress.authenticated_agent_id,
        )
        source = retain_source_authority_evidence(
            source=source, source_id=source_id, source_digest=source_digest, ingress=ingress,
        )
        if source_admission_source_digest(source) != source_digest:
            raise ValueError("native source digest does not match its Step-1 material")
        return source

    def read_exact_source() -> CanonicalMemoryRecord | None:
        with administration.verified_operation_context():
            verify_authority()
            source = plane.get_record(source_id)
            if source is None:
                return None
            if (
                not revoked.keeps_record(source)
                or source != build_source(source.timestamp)
                or admissions.recover_pending_admission(operation_fence=fence, authenticated_ingress=ingress) is None
            ):
                raise NativeSourceDeliveryConflict("native delivery conflicts with its retained admission")
            return source

    retained = read_exact_source()
    if retained is not None:
        return retained

    source = build_source(datetime.now(UTC))
    prepared = admissions.prepare_atomic(
        source=source, delivery_identity=identity, ingress=ingress, operation_id=event.event_id,
        outcome_kind="disabled", normalized_input=normalized.original_text.encode(), evidence_only=True,
    )
    writers = SemanticWriterAdmissionStore(plane, bounded_preplanning_ownership_manifest())
    binding = writers.commit_binding(writers.current())
    try:
        SemanticIngestionAtomicStore(plane, writers).publish_admitted_source(prepared=prepared, writer_binding=binding)
    except PreplanningStoreError:
        # Another publication may have retained the same delivery at its own server time.
        retained = read_exact_source()
        if retained is None:
            raise
        return retained
    retained = read_exact_source()
    if retained is None:
        raise ValueError("native source publication is unavailable")
    return retained
