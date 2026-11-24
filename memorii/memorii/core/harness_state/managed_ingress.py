"""Compose managed command authorization for host admission and durable replay."""

from __future__ import annotations

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
)
from memorii.core.persistence.runtime_contracts import (
    OperationOrigin,
    OperationOriginCoordinate,
    RuntimeCommandRequest,
)
from memorii.core.storage_administration.service import (
    InstallationControlState,
    RuntimePublicationState,
    StorageAdministrationService,
)


def authenticated_host_commands(
    administration: StorageAdministrationService,
    credentials: SidecarCredentialStore,
    secret: str,
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
        return ResolvedRuntimeCommandAuthority(resolved.principal, resolved.client_namespace)

    return ManagedRuntimeCommandService(administration, authorize=authorize)


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
        return ResolvedRuntimeCommandAuthority(resolved.principal, resolved.client_namespace)

    return ManagedRuntimeCommandService(administration, authorize=authorize)
