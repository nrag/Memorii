"""Read-only authorization and release for catalog inspection and recall."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, overload

from pydantic import ValidationError

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedIngressContext
from memorii.core.memory_evolution.writer_admission import CatalogBundleLocator
from memorii.core.memory_plane.models import CanonicalMemoryRecord
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.memory_plane.store import MemoryPlaneCorruptionError
from memorii.core.scoped_context.authority import ScopedHostReadAuthority
from memorii.core.semantic_ingestion.catalog_authority import (
    AgentLocalCatalogAuthorityScope,
    AuthenticatedPrincipalAgent,
    CatalogAuthorityError,
    CatalogAuthorityScope,
    StructuredFactReadAuthority,
    StructuredGrantState,
    structured_grant_state_record_id,
)
from memorii.core.semantic_ingestion.catalog_inspection import (
    CatalogReadDirection,
    CatalogReadStatus,
    CatalogRelationInspectionRequest,
    CatalogRelationInspectionResponse,
    StructuredRecallDiagnosisRequest,
    StructuredRecallDiagnosisResponse,
    normalize_relation_name,
    project_catalog_relations,
)
from memorii.core.semantic_ingestion.learned_relation import (
    OntologyActivation,
    OntologyCatalogVersion,
    learned_catalog_pointer_memory_id,
)
from memorii.core.semantic_ingestion.structured_fact_read import (
    CatalogBoundProjectionReadVerifier,
    read_current_catalog_bound_facts,
)
from memorii.core.storage_administration.revoked_identity_view import RevokedIdentityView
from memorii.domain.enums import CommitStatus, MemoryDomain, MemoryRecordVisibility


@dataclass(frozen=True)
class CatalogReadHostRequest:
    """Opaque, request-local authority obtained from the verified host."""

    handle: object
    task_id: str
    state_id: str
    installation_partition_id: str
    session_id: str
    authenticated: AuthenticatedPrincipalAgent
    fact_scope: str
    binding_is_current: Callable[[], bool]


def _current_grant_states(
    by_id: dict[str, CanonicalMemoryRecord],
    authorities: tuple[StructuredFactReadAuthority, ...],
) -> dict[tuple[str, str], StructuredGrantState]:
    states: dict[tuple[str, str], StructuredGrantState] = {}
    for authority in authorities:
        for kind, grant in (("fact", authority.fact_grant), ("catalog_visibility", authority.catalog_visibility_grant)):
            key = (kind, grant.grant_id)
            record = by_id.get(structured_grant_state_record_id(*key))
            if (
                record is None
                or record.source_kind != "semantic_ingestion_structured_grant_state"
                or record.domain is not MemoryDomain.EXECUTION
                or record.status is not CommitStatus.COMMITTED
                or record.visibility is not MemoryRecordVisibility.INTERNAL_CONTROL
            ):
                continue
            try:
                state = StructuredGrantState.model_validate(record.content.get("state"))
            except ValidationError:
                continue
            if state.active and state.grant_kind == kind and state.grant == grant:
                states[key] = state
    return states


def _has_agent_local_catalog_control(
    records: tuple[CanonicalMemoryRecord, ...], scope: AgentLocalCatalogAuthorityScope,
) -> bool:
    if any(record.memory_id == learned_catalog_pointer_memory_id(scope) for record in records):
        return True
    for record in records:
        if record.source_kind == "learned_ontology_activation_attempt_v1":
            try:
                attempt = OntologyActivation.model_validate(record.content.get("activation"))
            except ValidationError:
                continue
            if attempt.catalog_scope == scope and attempt.status == "selected":
                return True
    return False


@overload
def read_catalog_workflow(
    request: object, *, operation: Literal["inspect"], ingress: AuthenticatedIngressContext | None,
    host_request: CatalogReadHostRequest | None, host_authority: ScopedHostReadAuthority | None,
    memory_plane: MemoryPlaneService, locator: CatalogBundleLocator,
    now_provider: Callable[[], datetime], legacy_verifier: CatalogBoundProjectionReadVerifier,
    suppression_view: Callable[[tuple[CanonicalMemoryRecord, ...]], RevokedIdentityView] | None,
) -> CatalogRelationInspectionResponse: ...


@overload
def read_catalog_workflow(
    request: object, *, operation: Literal["diagnose"], ingress: AuthenticatedIngressContext | None,
    host_request: CatalogReadHostRequest | None, host_authority: ScopedHostReadAuthority | None,
    memory_plane: MemoryPlaneService, locator: CatalogBundleLocator,
    now_provider: Callable[[], datetime], legacy_verifier: CatalogBoundProjectionReadVerifier,
    suppression_view: Callable[[tuple[CanonicalMemoryRecord, ...]], RevokedIdentityView] | None,
) -> StructuredRecallDiagnosisResponse: ...


def read_catalog_workflow(
    request: object, *, operation: Literal["inspect", "diagnose"],
    ingress: AuthenticatedIngressContext | None,
    host_request: CatalogReadHostRequest | None, host_authority: ScopedHostReadAuthority | None,
    memory_plane: MemoryPlaneService, locator: CatalogBundleLocator,
    now_provider: Callable[[], datetime], legacy_verifier: CatalogBoundProjectionReadVerifier,
    suppression_view: Callable[[tuple[CanonicalMemoryRecord, ...]], RevokedIdentityView] | None,
) -> CatalogRelationInspectionResponse | StructuredRecallDiagnosisResponse:
    from memorii.core.persistence.factory import ManagedPartitionError
    from memorii.core.storage_administration.service import StorageAdministrationError

    response_type = CatalogRelationInspectionResponse if operation == "inspect" else StructuredRecallDiagnosisResponse

    def empty(status: CatalogReadStatus):
        return response_type.model_validate({"status": status})

    if host_authority is None or suppression_view is None:
        return empty(CatalogReadStatus.UNAVAILABLE)
    if host_request is None or ingress is None:
        return empty(CatalogReadStatus.DENIED)
    authenticated = host_request.authenticated
    principal = ingress.delivery_principal_binding
    if (
        principal.principal_subject_id != authenticated.principal_id
        or principal.tenant_partition_id != host_request.installation_partition_id
        or ingress.authenticated_agent_id != authenticated.agent_id
        or host_request.fact_scope not in ingress.current_authorized_scopes.scopes
        or f"session:{host_request.session_id}" not in ingress.required_outcome_scopes.scopes
        or not host_request.binding_is_current()
    ):
        return empty(CatalogReadStatus.DENIED)
    grant = host_authority.resolve(
        host_request.handle, task_id=host_request.task_id, state_id=host_request.state_id,
    )
    if grant is None or not grant.rows or any(
        row.domain is not MemoryDomain.SEMANTIC
        or row.user_id != authenticated.principal_id
        or row.agent_id not in (None, authenticated.agent_id)
        or row.session_id not in (None, host_request.session_id)
        for row in grant.rows
    ):
        return empty(CatalogReadStatus.DENIED)

    def read(revision: int, records: tuple[CanonicalMemoryRecord, ...]):
        by_id = {record.memory_id: record for record in records}
        child = AgentLocalCatalogAuthorityScope(
            principal_id=authenticated.principal_id, agent_id=authenticated.agent_id,
        )
        base = CatalogAuthorityScope(schema_version=1, kind="base")
        authorities = tuple(
            authority for authority in grant.structured_fact_read_authorities
            if authority.authenticated == authenticated
            and authority.fact_grant.fact_scope == host_request.fact_scope
            and authority.catalog_visibility_grant.catalog_scope in (base, child)
            and authority.paired_evaluation_authority is None
        )
        states = _current_grant_states(by_id, authorities)
        current = {
            authority.catalog_visibility_grant.catalog_scope: authority for authority in authorities
            if (fact_state := states.get(("fact", authority.fact_grant.grant_id))) is not None
            and fact_state.grant == authority.fact_grant
            and (catalog_state := states.get(("catalog_visibility", authority.catalog_visibility_grant.grant_id))) is not None
            and catalog_state.grant == authority.catalog_visibility_grant
        }

        def released() -> bool:
            return host_authority.authorize_release(grant) is not None and host_request.binding_is_current()

        def finish(status: CatalogReadStatus):
            return empty(status if released() else CatalogReadStatus.DENIED)

        if len(by_id) != len(records):
            return finish(CatalogReadStatus.UNAVAILABLE)
        if not current:
            return finish(CatalogReadStatus.DENIED)
        try:
            if operation == "inspect":
                lookup = CatalogRelationInspectionRequest.model_validate(request).root
                exact = None
            else:
                lookup = None
                exact = StructuredRecallDiagnosisRequest.model_validate(request).root
        except ValidationError:
            return finish(CatalogReadStatus.INVALID_REQUEST)
        if exact is not None and exact.kind == "unresolved":
            return finish(CatalogReadStatus.NEEDS_CLARIFICATION)

        scope = child if _has_agent_local_catalog_control(records, child) else base
        if scope not in current:
            return finish(CatalogReadStatus.DENIED)
        try:
            bundle, _ = locator.locate_selected(records, scope=scope, authenticated=authenticated)
            # Early learned versions identify a parent catalog digest, which
            # cannot distinguish the seed from the packaged child version.
            if isinstance(bundle.version, OntologyCatalogVersion):
                return finish(CatalogReadStatus.UNAVAILABLE)
            if (
                exact is not None and exact.expected_catalog_version_digest is not None
                and exact.expected_catalog_version_digest != bundle.version.version_digest
            ):
                return finish(CatalogReadStatus.CATALOG_CHANGED)
            if exact is not None and exact.predicate_id not in bundle.version.predicate_ids:
                return finish(CatalogReadStatus.UNSUPPORTED_PREDICATE)
            descriptors = project_catalog_relations(bundle)
        except (CatalogAuthorityError, OSError, ValidationError):
            return finish(CatalogReadStatus.UNAVAILABLE)
        if lookup is not None:
            if lookup.kind == "predicate_id":
                matches = tuple(item for item in descriptors if lookup.predicate_id == item.predicate_id)
            else:
                name = normalize_relation_name(lookup.name)
                matches = tuple(item for item in descriptors if name == item.label or name in item.lookup_aliases)
            if not matches:
                return finish(CatalogReadStatus.NO_MATCH)
            if not released():
                return empty(CatalogReadStatus.DENIED)
            return CatalogRelationInspectionResponse.model_validate({
                "status": CatalogReadStatus.MATCHED if len(matches) == 1 else CatalogReadStatus.AMBIGUOUS,
                "catalog_version_digest": bundle.version.version_digest,
                "relations": matches,
            })

        assert exact is not None
        descriptor = next(item for item in descriptors if item.predicate_id == exact.predicate_id)
        pending = read_current_catalog_bound_facts(
            records=records, revision=revision, grant=grant, current_authorities=current,
            grant_states=states, locator=locator, legacy_verifier=legacy_verifier,
            predicate_id=exact.predicate_id, subject_id=exact.subject_entity_id,
            symmetric=descriptor.read_direction is CatalogReadDirection.SYMMETRIC_VIEW,
            now=now_provider(),
        )
        if not released():
            return empty(CatalogReadStatus.DENIED)
        view = suppression_view(records)
        items = pending.release(view)
        if items is None:
            return empty(CatalogReadStatus.UNAVAILABLE)
        if not items:
            return empty(CatalogReadStatus.NO_READABLE_FACT)
        return StructuredRecallDiagnosisResponse.model_validate({
            "status": CatalogReadStatus.FOUND, "items": items,
        })

    try:
        result = memory_plane.read_snapshot_linearized(read)
    except (
        CatalogAuthorityError, ManagedPartitionError, MemoryPlaneCorruptionError, StorageAdministrationError,
        OSError, sqlite3.Error, ValueError,
    ):
        return empty(CatalogReadStatus.UNAVAILABLE)
    return result if isinstance(result, response_type) else empty(CatalogReadStatus.UNAVAILABLE)
