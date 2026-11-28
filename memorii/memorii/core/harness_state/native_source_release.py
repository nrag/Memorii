"""Bind one committed native observation to an explicit owner release."""

from memorii.core.harness_state.consumer import ManagedSpoolEntry
from memorii.core.harness_state.native_sources import resolve_native_source_binding
from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext
from memorii.core.provider.runtime_source_authority import RuntimeSourceAuthorityError
from memorii.core.provider.runtime_source_release import (
    RuntimeSourceReleaseAuthority,
    RuntimeSourceReleaseGrant,
)
from memorii.core.storage_administration.operator import OwnerCapability, require_owner_capability
from memorii.core.storage_administration.service import StorageAdministrationService


def issue_native_source_release(
    administration: StorageAdministrationService, *, capability: OwnerCapability, entry: ManagedSpoolEntry,
) -> RuntimeSourceReleaseGrant:
    """Issue the canonical lifecycle grant from the original signed native intake."""
    require_owner_capability(administration, capability)
    delivery = entry.delivery
    request = delivery.command
    proof = entry.operation_origin
    origin = proof.coordinate
    if (
        entry.state != "committed"
        or request.kind != "record_observation"
        or request.operation_id != origin.operation_id
        or request.managed_intent_digest() != origin.request_digest
        or delivery.transport_message_id != request.operation_id
        or delivery.producer_binding != origin.client_namespace
    ):
        raise RuntimeSourceAuthorityError("denied: expected one committed native observation entry")

    with administration.verified_operation_context() as (state, finalized):
        require_owner_capability(administration, capability)
        if (
            state.mode != "active"
            or origin.installation_id != finalized.installation_id
            or origin.repository_id != finalized.repository_id
            or origin.generation_id != finalized.data_generation_id
            or not administration.verify_operation_origin(proof)
        ):
            raise RuntimeSourceAuthorityError("denied: native observation proof is unavailable")
        ingress, fence, binding = resolve_native_source_binding(administration, request, origin, finalized)

    def resolve_ingress() -> AuthenticatedIngressContext | None:
        _, finalized = administration.current_publication_in_fence()
        current = resolve_native_source_binding(administration, request, origin, finalized)
        return current[0] if current == (ingress, fence, binding) else None

    return RuntimeSourceReleaseAuthority(administration).issue(
        capability=capability,
        observation_origin=proof,
        binding=binding,
        operation_fence=fence,
        resolve_ingress=resolve_ingress,
    )
