"""Compose managed command authorization for host admission and durable replay."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext, OperationFenceBinding
    from memorii.core.provider.runtime_source_authority import RuntimeSourceTaskBinding

from memorii.core.harness_state.credentials import SidecarCredentialStore
from memorii.core.harness_state.write_authority import (
    HostCommandAuthorityError,
    ManagedHostCommandAuthority,
)
from memorii.core.persistence.runtime_api import (
    CommandAuthorityPurpose,
    ManagedRuntimeCommandService,
    ResolvedRuntimeCommandAuthority,
    RuntimeCommandError,
    RuntimeObservationSource,
)
from memorii.core.persistence.runtime_contracts import (
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeCommandRequest,
    RuntimeSourceAdmissionReceipt,
)
from memorii.core.persistence.runtime_repository import RuntimeStateRepository
from memorii.core.storage_administration.revoked_identity_view import RefreshingRevokedIdentityView
from memorii.core.storage_administration.service import (
    InstallationControlState,
    RuntimePublicationState,
    StorageAdministrationService,
)


def authenticated_host_commands(
    administration: StorageAdministrationService,
    credentials: SidecarCredentialStore,
    secret: str,
    *,
    observation_source: RuntimeObservationSource | None = None,
    enrolled_source_append: bool = False,
) -> ManagedRuntimeCommandService:
    """Resolve authority afresh under the runtime owner's publication fence."""
    grants = ManagedHostCommandAuthority(administration)

    def authorize(
        request: RuntimeCommandRequest,
        purpose: CommandAuthorityPurpose,
        origin: OperationOriginCoordinate | None,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ResolvedRuntimeCommandAuthority | None:
        # Older generations require explicit review by the restore owner.
        if purpose == "historical_release":
            return None
        credentials.verify_permissions()
        credential = credentials.credential_for(secret)
        if credential is None:
            return None
        try:
            resolved = grants.resolve_for_credential_in_verified_context(
                credential=credential,
                request=request,
                state=state,
                finalized=finalized,
            )
        except HostCommandAuthorityError as exc:
            code = str(exc).partition(":")[0]
            if code == "unsupported_configuration":
                raise RuntimeCommandError("unsupported_configuration: ambiguous command authority") from exc
            return None
        return ResolvedRuntimeCommandAuthority(resolved.principal, resolved.client_namespace, resolved)

    return ManagedRuntimeCommandService(
        administration, authorize=authorize, observation_source=observation_source,
        enrolled_source_append=enrolled_source_append,
    )


def authenticated_provider_observations(
    administration: StorageAdministrationService,
    credentials: SidecarCredentialStore,
    secret: str,
    *,
    binding: RuntimeSourceTaskBinding,
    operation_fence: OperationFenceBinding,
    resolve_ingress: Callable[[], AuthenticatedIngressContext | None],
) -> ManagedRuntimeCommandService:
    """Compose an embedded owner path with both live provider and runtime authority."""
    from memorii.core.provider.runtime_source_authority import RuntimeSourceAuthorityError, resolve_runtime_source

    revoked = RefreshingRevokedIdentityView(administration.installation_root / "control")

    def observation_source(
        connection: sqlite3.Connection, repository: RuntimeStateRepository, request: RuntimeCommandRequest,
        origin: OperationOriginCoordinate, finalized: RuntimePublicationState,
    ) -> RuntimeSourceAdmissionReceipt:
        if request.task_id is None or request.source_digest is None:
            raise RuntimeCommandError("invalid_request: observation requires a task and provider source digest")
        try:
            evidence = resolve_runtime_source(
                connection, repository.partition, finalized=finalized, origin=origin,
                runtime_task_id=request.task_id, source_digest=request.source_digest,
                operation_fence=operation_fence, resolve_ingress=resolve_ingress, binding=binding,
                revoked=revoked, now=datetime.now(UTC),
            )
        except RuntimeSourceAuthorityError as exc:
            raise RuntimeCommandError("denied: verified provider admission is unavailable") from exc
        return RuntimeSourceAdmissionReceipt(
            task_id=request.task_id, source_id=evidence.source_ref.source_id,
            source_record_digest=evidence.source_ref.source_digest, provider_source_digest=evidence.source_digest,
            admission_index_digest=evidence.admission_index_digest, delivery_key_digest=evidence.delivery_key_digest,
            source_write_revision=evidence.source_write_revision, source_type=evidence.source_type,
            modalities=evidence.modalities, retained_at=evidence.retained_at,
        )

    return authenticated_host_commands(administration, credentials, secret, observation_source=observation_source)


def spooled_host_commands(
    administration: StorageAdministrationService,
    proof: OperationOrigin,
) -> ManagedRuntimeCommandService:
    """Resolve the originally bound namespace without recovering a bearer."""
    grants = ManagedHostCommandAuthority(administration)

    def authorize(
        request: RuntimeCommandRequest,
        purpose: CommandAuthorityPurpose,
        origin: OperationOriginCoordinate | None,
        state: InstallationControlState,
        finalized: RuntimePublicationState,
    ) -> ResolvedRuntimeCommandAuthority | None:
        if origin is None or purpose in ("prepare", "historical_release") or origin != proof.coordinate:
            return None
        if not administration.verify_operation_origin(proof):
            return None
        if origin.generation_id != finalized.data_generation_id:
            raise RuntimeCommandError("needs_reconciliation: operation belongs to another generation")
        try:
            resolved = grants.resolve_persisted_namespace_in_verified_context(
                principal=origin.principal,
                client_namespace=origin.client_namespace,
                request=request,
                state=state,
                finalized=finalized,
            )
        except HostCommandAuthorityError:
            return None
        return ResolvedRuntimeCommandAuthority(resolved.principal, resolved.client_namespace, resolved)

    from memorii.core.harness_state.native_sources import resolve_enrolled_runtime_source

    observation_source = (
        partial(resolve_enrolled_runtime_source, administration)
        if proof.coordinate.operation_id.startswith("native-source:") else None
    )
    return ManagedRuntimeCommandService(
        administration, authorize=authorize, observation_source=observation_source,
        enrolled_source_append=observation_source is not None,
    )
