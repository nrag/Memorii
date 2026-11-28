"""Native source admission and managed observation for the reference workload."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from memorii.core.filesystem_storage.bundle import FilesystemStorageBundle
from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.managed_ingress import authenticated_provider_observations
from memorii.core.harness_state.write_authority import HostCommandGrantRequest, ManagedHostCommandAuthority
from memorii.core.memory_evolution.admission import GovernedSourceAdmissionService, source_admission_source_digest
from memorii.core.memory_evolution.atomic_store import SemanticIngestionAtomicStore
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContext,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    DeliveryIdentity,
    DeliveryPrincipalBinding,
    OperationFenceBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_evolution.ingestion_time_clock import IngestionTimeClock
from memorii.core.memory_evolution.writer_admission import (
    SemanticWriterAdmissionStore,
    bounded_preplanning_ownership_manifest,
)
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.store import record_digest
from memorii.core.persistence.runtime_contracts import NodeEvidenceReference, RuntimeCommandRequest
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.provider.ingestion import ProviderIngestionCoordinator
from memorii.core.provider.models import ProviderEvent, ProviderOperation
from memorii.core.provider.runtime_source_authority import RuntimeSourceTaskBinding
from memorii.core.semantic_ingestion.canonical_evidence_arena import CanonicalEvidenceArena
from memorii.core.storage_administration.operator import mint_owner_capability
from memorii.core.storage_administration.service import InitializationReceipt, StorageAdministrationService

from tests.support.reference_capacity import FIXTURE_START, SourceInput

REFERENCE_PRINCIPAL = "reference-capacity-owner"
REFERENCE_NAMESPACE = "reference-capacity-provider"
_TENANT = "reference-capacity-tenant"


class ReferenceSourceError(RuntimeError):
    """The installed native source owner did not produce exact fixture evidence."""


def reference_delivery(source: SourceInput) -> tuple[str, AuthenticatedIngressContext, DeliveryIdentity]:
    binding = DeliveryPrincipalBinding.create(
        principal_subject_id=REFERENCE_PRINCIPAL, tenant_partition_id=_TENANT, provider_identity="reference-capacity",
    )
    session = f"{source.task_id}:session"
    scopes = RequiredOutcomeScopeSet.create(
        tenant_partition_id=_TENANT, scopes={f"session:{session}", f"user:{REFERENCE_PRINCIPAL}"},
    )
    ingress = AuthenticatedIngressContext(
        delivery_principal_binding=binding,
        required_outcome_scopes=scopes,
        current_authorized_scopes=scopes,
        language_declaration="en",
        language_evidence_kind="authenticated_host_declaration",
        language_evidence_trust="trusted",
        language_governance_agreement="agrees",
        semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
            classification="trial", provider="reference-capacity", model="none", region="local",
            retention_mode="store_false", training_use=False,
        ),
        semantic_source_authority=AuthenticatedSemanticSourceAuthority(
            authority_class="official", authenticated_provenance_class="authenticated_user",
            policy_revision="reference-capacity", provenance_digest="b" * 64,
        ),
    )
    return session, ingress, DeliveryIdentity.create(binding, source.coordinate)


class ReferenceSourceCapture:
    """Drive the installed capture and authenticated runtime owners without a model."""

    def __init__(
        self,
        administration: StorageAdministrationService,
        installation: InitializationReceipt | None = None,
        task_ids: Sequence[str] = (),
    ) -> None:
        self._administration = administration
        self._installation = installation
        self._timestamp = FIXTURE_START
        root = administration.installation_root
        self._memory_plane = FilesystemStorageBundle.from_managed_root(root, administration).build_memory_plane_service()
        clock = IngestionTimeClock(identity="reference-capacity-fixture", now_provider=self._now)
        writers = SemanticWriterAdmissionStore(
            self._memory_plane, bounded_preplanning_ownership_manifest(), now_provider=clock.now_utc,
        )
        writers.create_initial_evidence_only(
            admission_id="reference-capacity-writer", writer_implementation_fingerprint="reference-capacity-writer",
            graph_schema_fingerprint="reference-capacity-graph",
        )
        self._provider = ProviderIngestionCoordinator(
            memory_plane=self._memory_plane,
            admission_service=GovernedSourceAdmissionService(self._memory_plane),
            bootstrap_profile=None,
            bootstrap_unavailable_reason="invalid_config",
            atomic_store=SemanticIngestionAtomicStore(self._memory_plane, writers, ingestion_time_clock=clock),
            writer_admission=writers,
            clock=clock,
        )
        self._credentials = None
        self._secret = None
        if task_ids:
            if installation is None:
                raise ValueError("reference observation grant needs the installation coordinates")
            self._credentials = SidecarCredentialStore(root / "control" / "credentials")
            credential, self._secret = self._credentials.issue(REFERENCE_PRINCIPAL)
            ManagedHostCommandAuthority(administration).issue(HostCommandGrantRequest(
                grant_id="reference-capacity-observation", credential_id=credential.credential_id,
                principal=credential.principal, client_namespace=REFERENCE_NAMESPACE,
                allowed_kinds=("record_observation",), allowed_task_ids=tuple(task_ids),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            ), capability=mint_owner_capability(administration, REFERENCE_PRINCIPAL))

    def _now(self) -> datetime:
        return self._timestamp

    def retain(self, source: SourceInput, body: str) -> CanonicalMemoryRecord:
        """Capture one native transcript without publishing a runtime observation."""
        self._timestamp = source.timestamp
        session, ingress, identity = reference_delivery(source)
        event = ProviderEvent(
            event_id=source.coordinate, operation=ProviderOperation.CHAT_USER_TURN, role="user",
            content=body, session_id=session, task_id=source.task_id,
            user_id=REFERENCE_PRINCIPAL, timestamp=source.timestamp,
        )
        with CanonicalEvidenceArena(enabled=False) as arena:
            result, _, _ = self._provider.ingest(
                event, defer_assertions=True, authenticated_ingress=ingress, canonical_evidence_arena=arena,
            )
        expected_id = f"semantic_ingestion:source:{identity.delivery_key_digest}"
        if result.transcript_ids != [expected_id] or result.candidate_ids:
            raise ReferenceSourceError("native provider source admission did not retain the expected delivery")
        retained = self._memory_plane.get_record(expected_id)
        if retained is None or retained.text != event.content:
            raise ReferenceSourceError("native provider retained bytes differ from the source input")
        return retained

    def capture(self, source: SourceInput) -> NodeEvidenceReference:
        installation, credentials, secret = self._installation, self._credentials, self._secret
        if installation is None or credentials is None or secret is None:
            raise ReferenceSourceError("reference runtime observation authority is unavailable")
        retained = self.retain(source, source.body().decode("ascii"))
        session, ingress, identity = reference_delivery(source)
        expected_id = retained.memory_id
        digest = source_admission_source_digest(retained)
        fence = OperationFenceBinding.create(
            operation_id=source.coordinate, source_id=expected_id, source_digest=digest, delivery_identity=identity,
        )
        binding = RuntimeSourceTaskBinding(
            installation_id=installation.installation_id, repository_id=installation.repository_id,
            generation_id=installation.data_generation_id, runtime_task_id=source.task_id,
            runtime_principal=REFERENCE_PRINCIPAL, client_namespace=REFERENCE_NAMESPACE,
            provider_task_id=source.task_id, provider_session_id=session,
            provider_principal_binding_digest=ingress.delivery_principal_binding.binding_digest,
            delivery_key_digest=identity.delivery_key_digest,
        )
        runtime = authenticated_provider_observations(
            self._administration, credentials, secret, binding=binding, operation_fence=fence,
            resolve_ingress=lambda: ingress,
        )
        task = RuntimeStateRepository(self._administration.partition()).get_task(source.task_id)
        if task is None:
            raise ReferenceSourceError("native source has no referent runtime task")
        command = RuntimeCommandRequest(
            kind="record_observation", operation_id=f"{source.coordinate}:observe",
            task_id=source.task_id, expected_revision=task.version, source_digest=digest,
        )
        receipt = runtime.dispatch(command, operation_origin=runtime.prepare(command))
        expected_digest = record_digest(retained)
        admission = receipt.source_admission
        if (
            receipt.status != "committed" or admission is None or admission.source_id != expected_id
            or admission.source_record_digest != expected_digest or admission.provider_source_digest != digest
        ):
            raise ReferenceSourceError("signed runtime receipt has no exact native source admission")
        return NodeEvidenceReference(source_id=expected_id, source_digest=expected_digest)
