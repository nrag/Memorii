"""Verified host composition for the request-local catalog read port."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Protocol, TypeVar

from memorii.core.memory_evolution.ingestion_contracts import AuthenticatedHostIngress
from memorii.core.provider.catalog_read_workflow import CatalogReadHostRequest
from memorii.core.provider.service import ProviderMemoryService
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority, ScopedNamespaceGrantRow
from memorii.core.semantic_ingestion.catalog_authority import (
    AgentLocalCatalogAuthorityScope,
    AuthenticatedPrincipalAgent,
    CatalogAuthorityCoordinate,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    StructuredFactReadAuthority,
)
from memorii.core.semantic_ingestion.catalog_inspection import (
    CatalogRelationInspectionResponse,
    StructuredRecallDiagnosisResponse,
)
from memorii.domain.enums import MemoryDomain


@dataclass(frozen=True, kw_only=True)
class CatalogReadGrantReference:
    catalog_scope: CatalogAuthorityCoordinate
    fact_grant_id: str
    fact_grant_version: int
    catalog_grant_id: str
    catalog_grant_version: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.catalog_scope, (CatalogAuthorityScope, AgentLocalCatalogAuthorityScope))
            or not isinstance(self.fact_grant_id, str) or not self.fact_grant_id
            or not isinstance(self.catalog_grant_id, str) or not self.catalog_grant_id
            or type(self.fact_grant_version) is not int or self.fact_grant_version < 1
            or type(self.catalog_grant_version) is not int or self.catalog_grant_version < 1
        ):
            raise ValueError("catalog read grant reference is invalid")


@dataclass(frozen=True, kw_only=True)
class CatalogReadOptIn:
    """Installation operator's trusted read configuration."""

    installation_id: str
    storage_root: Path
    user_id: str
    agent_id: str
    fact_scope: str
    rows: tuple[ScopedNamespaceGrantRow, ...]
    grant_references: tuple[CatalogReadGrantReference, ...]


@dataclass(frozen=True)
class CatalogReadBinding:
    inspect_catalog_relation: Callable[[object], CatalogRelationInspectionResponse]
    diagnose_structured_recall: Callable[[object], StructuredRecallDiagnosisResponse]


_ReadResponse = TypeVar("_ReadResponse", covariant=True)


class _ReadOperation(Protocol[_ReadResponse]):
    def __call__(
        self, request: object, *, authenticated_host_ingress: AuthenticatedHostIngress | None,
        host_read_request: CatalogReadHostRequest | None,
    ) -> _ReadResponse: ...


def bind_catalog_read(
    *,
    service: ProviderMemoryService,
    authority: InProcessScopedReadAuthority,
    installation_id: str,
    storage_root: Path,
    raw_user_id: str | None,
    authenticated: AuthenticatedPrincipalAgent,
    current_opt_in: Callable[[], object],
    current_session: Callable[[], object],
    installation_is_current: Callable[[], bool],
    issue_ingress: Callable[[object], AuthenticatedHostIngress],
) -> CatalogReadBinding:
    """Compose read callbacks from a verified host, with no write authority."""

    def with_authority(request: object, operation: _ReadOperation[_ReadResponse]) -> _ReadResponse:
        opt_in = current_opt_in()
        session = current_session()
        if (
            not isinstance(opt_in, CatalogReadOptIn)
            or not isinstance(session, str) or not session.strip()
            or not isinstance(raw_user_id, str) or not raw_user_id.strip()
            or opt_in.installation_id != installation_id
            or not isinstance(opt_in.storage_root, Path)
            or opt_in.storage_root.resolve() != storage_root.resolve()
            or opt_in.user_id != raw_user_id
            or opt_in.agent_id != authenticated.agent_id
            or opt_in.fact_scope != f"user:{authenticated.principal_id}"
            or not isinstance(opt_in.rows, tuple) or not opt_in.rows
            or not isinstance(opt_in.grant_references, tuple) or not opt_in.grant_references
            or any(
                not isinstance(row, ScopedNamespaceGrantRow)
                or row.domain is not MemoryDomain.SEMANTIC
                or row.user_id != authenticated.principal_id
                or row.agent_id not in (None, authenticated.agent_id)
                or row.session_id not in (None, session)
                for row in opt_in.rows
            )
            or any(not isinstance(ref, CatalogReadGrantReference) for ref in opt_in.grant_references)
            or len({ref.catalog_scope.model_dump_json() for ref in opt_in.grant_references}) != len(opt_in.grant_references)
            or not installation_is_current()
        ):
            return operation(request, authenticated_host_ingress=None, host_read_request=None)

        def binding_is_current() -> bool:
            return (
                current_session() == session
                and current_opt_in() == opt_in
                and installation_is_current()
            )

        now = datetime.now(UTC)
        task = "catalog-read"
        try:
            pairs = tuple(
                StructuredFactReadAuthority(
                    authenticated=authenticated,
                    fact_grant=FactScopeGrant(
                        grant_id=ref.fact_grant_id,
                        grant_version=ref.fact_grant_version,
                        fact_scope=opt_in.fact_scope,
                        authenticated=authenticated,
                    ),
                    catalog_visibility_grant=CatalogOwnerVisibilityGrant(
                        grant_id=ref.catalog_grant_id,
                        grant_version=ref.catalog_grant_version,
                        catalog_scope=ref.catalog_scope,
                        authenticated=authenticated,
                        purpose="visibility_status",
                    ),
                )
                for ref in opt_in.grant_references
            )
            ingress = issue_ingress(SimpleNamespace(
                hook="catalog_read", session_id=session, user_id=authenticated.principal_id,
                agent_id=authenticated.agent_id, received_at=now,
            ))
            handle = authority.provision(
                host_task_id=task, host_state_id=session, rows=opt_in.rows,
                structured_fact_read_authorities=pairs, expires_at=now + timedelta(minutes=1),
            )
        except (TypeError, ValueError):
            return operation(request, authenticated_host_ingress=None, host_read_request=None)
        try:
            return operation(
                request,
                authenticated_host_ingress=ingress,
                host_read_request=CatalogReadHostRequest(
                    handle=handle, task_id=task, state_id=session,
                    installation_partition_id=f"local:{installation_id}",
                    session_id=session, authenticated=authenticated, fact_scope=opt_in.fact_scope,
                    binding_is_current=binding_is_current,
                ),
            )
        finally:
            authority.revoke(handle)

    return CatalogReadBinding(
        inspect_catalog_relation=lambda request: with_authority(request, service.inspect_catalog_relation),
        diagnose_structured_recall=lambda request: with_authority(request, service.diagnose_structured_recall),
    )
