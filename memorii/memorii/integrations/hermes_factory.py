"""First-party Hermes factory for the installation-bound Level 2 trial.

This is an admission boundary only.  It verifies package profile material and
the operator's sidecar before constructing the existing provider service.  The
semantic runtime, completed-turn admission, and protected recall are composed
by later milestones, so this binding deliberately refuses turn ingress.
"""

from __future__ import annotations

import json
import os
import time
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedHostIngress,
    AuthenticatedIngressContext,
    AuthenticatedOriginLineageEvidence,
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
    encode_typed_value,
)
from memorii.core.memory_evolution.models import EntityType
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority
from memorii.core.semantic_ingestion.catalog_authority import (
    AuthenticatedPrincipalAgent,
    CatalogAuthorityScope,
    CatalogOwnerVisibilityGrant,
    FactScopeGrant,
    ResolvedStructuredSubmissionAuthority,
    SourceScopeGrant,
    StructuredFactReadAuthority,
    StructuredSubmissionAuthorityRequest,
    ThreePredicateSeedCatalogAuthorityRepository,
)
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    CurrentReleaseBootstrapV3HostMaterialBuilder,
    local_level2_bootstrap_authorization_from_sidecar,
)
from memorii.core.semantic_ingestion.project_assertions_profile import load_project_assertions_bundle
from memorii.core.user_context.preference_delegations import PreferenceDelegationRepository
from memorii.core.user_context.preferences import (
    PreferenceAccessPolicy,
    PreferenceHolderAuthority,
    PreferenceService,
)
from memorii.integrations.hermes_local_authority import (
    LocalLevel2AuthorityError,
    load_local_level2_authority,
    load_local_structured_tool_authority,
)
from memorii.integrations.hermes_runtime_binding import HermesAuthenticatedOriginReceipt

_PREFERENCE_TOPIC_TYPES = {
    "ProductService": EntityType.PRODUCT_SERVICE,
    "Asset": EntityType.ASSET,
    "Place": EntityType.PLACE,
}


def _preference_topic_identity_resolver(
    *,
    service,
    holder_user_id: str,
):
    """Bind Preferences to the current canonical semantic entity owner."""

    def identity_is_current(
        requested_holder_id: str,
        canonical_topic_id: str,
        topic_type: str,
        topic_quote: str,
    ) -> bool:
        expected_type = _PREFERENCE_TOPIC_TYPES.get(topic_type)
        if requested_holder_id != holder_user_id or expected_type is None:
            return False
        quote_key = " ".join(unicodedata.normalize("NFKC", topic_quote).casefold().split())
        return bool(quote_key) and service.current_semantic_entity_matches(
            canonical_entity_id=canonical_topic_id,
            asserted_type=expected_type.value,
            normalized_alias_key=quote_key,
            expected_fact_scope=f"user:{holder_user_id}",
        )

    return identity_is_current


def build_local_level2_runtime_binding(context: object) -> object:
    """Construct the standard verified first-party Hermes runtime binding."""
    return _build_local_level2_runtime_binding(context)


def _build_local_level2_runtime_binding(
    context: object,
    *,
    _provision_structured_authority: bool = True,
    _allow_existing_operator_binding: bool = False,
) -> object:
    """Construct one verified, first-party Hermes binding without model I/O.

    The bridge supplies a typed context, but this module avoids importing the
    optional Hermes ABC at import time.  Local authority verification precedes
    memory-plane construction, service startup, credentials, and any remote
    transport construction.
    """

    hermes_home = getattr(context, "hermes_home", None)
    storage_root = getattr(context, "storage_root", None)
    if hermes_home is None or storage_root is None:
        raise TypeError("Hermes factory context is invalid")
    context_kind = _require_local_cli_context(context)

    bundle = load_project_assertions_bundle()
    sidecar = load_local_level2_authority(hermes_home=hermes_home)
    authorization = sidecar.get("authorization")
    if not isinstance(authorization, dict) or {
        field: authorization.get(field) for field in bundle.profile_digests
    } != dict(bundle.profile_digests):
        raise LocalLevel2AuthorityError("local Level 2 authority profile binding is invalid")

    now = datetime.now(UTC)
    authorization = local_level2_bootstrap_authorization_from_sidecar(sidecar, now=now)
    operator_id = (
        "memorii:hermes:operator:"
        + sha256((f"memorii.hermes.local-level2-operator.v1:{authorization.installation_id}").encode()).hexdigest()
    )
    agent_id = _canonical_agent_id(getattr(context, "agent_identity", None))
    primary_agent_id = _bind_single_local_operator_context(
        storage_root=storage_root,
        installation_id=authorization.installation_id,
        raw_user_id=getattr(context, "user_id", None),
        agent_id=agent_id,
        context_kind=context_kind,
        allow_existing_operator_binding=_allow_existing_operator_binding,
    )
    ingress_resolver = _LocalLevel2IngressResolver(
        installation_id=authorization.installation_id,
        operator_id=operator_id,
    )

    def authority_is_current() -> bool:
        try:
            current_bundle = load_project_assertions_bundle()
            current = load_local_level2_authority(hermes_home=hermes_home)
            current_authorization = local_level2_bootstrap_authorization_from_sidecar(current, now=datetime.now(UTC))
            current = current_authorization == authorization and dict(current_bundle.profile_digests) == dict(
                bundle.profile_digests
            )
            if not current or context_kind != "delegated":
                return current
            current_plane = MemoryPlaneService(
                record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane")
            )
            return PreferenceDelegationRepository(current_plane).active(operator_id, agent_id)
        except (OSError, TypeError, ValueError):
            return False

    try:
        if context_kind != "primary":
            raise LocalLevel2AuthorityError("delegated preference agents cannot submit semantic facts")
        load_local_structured_tool_authority(hermes_home=hermes_home, now=now)
    except LocalLevel2AuthorityError:
        structured_resolver = None
    else:
        structured_resolver = _LocalLevel2StructuredSubmissionResolver(
            installation_id=authorization.installation_id,
            operator_id=operator_id,
            agent_id=agent_id,
            project_task_id=_project_task_id(
                authorization.installation_id, bundle.profile_digests["semantic_contract_digest"]
            ),
            authority_is_current=authority_is_current,
            structured_tool_is_current=lambda: _structured_tool_is_current(hermes_home),
        )

    capability, verifier = CurrentReleaseBootstrapV3HostMaterialBuilder.build_capability(
        authorization=authorization,
        now=now,
        authenticated_ingress_resolver=ingress_resolver,
        structured_submission_authority_resolver=structured_resolver,
        authorization_is_current=authority_is_current,
    )
    memory_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane"))
    delegation_repository = PreferenceDelegationRepository(memory_plane)
    if context_kind == "delegated" and not delegation_repository.active(operator_id, agent_id):
        raise LocalLevel2AuthorityError("Hermes preference agent delegation is unavailable")
    scoped_read_authority = InProcessScopedReadAuthority(now_provider=lambda: datetime.now(UTC))
    service = build_provider_memory_service_from_env(
        memory_plane=memory_plane,
        host_bootstrap_capability=capability,
        host_bootstrap_material_verifier=verifier,
        scoped_read_authority=scoped_read_authority,
    )
    if service._composed_semantic_runtime is None:
        raise RuntimeError(
            "Hermes local Level 2 semantic runtime is unavailable: " + service._bootstrap_unavailable_reason
        )
    # Both the seed and generated default bundle are governed startup fences.
    # A captured turn therefore pins one persisted catalog version before the
    # tool schema is advertised.
    service.ensure_catalog_seed_genesis()
    service.ensure_default_catalog_release()
    preference_service = PreferenceService(
        memory_plane=memory_plane,
        policy=PreferenceAccessPolicy(
            holder_authorities=(
                PreferenceHolderAuthority(holder_user_id=operator_id, primary_agent_id=primary_agent_id),
            ),
            grants=(),
            delegation_repository=delegation_repository,
        ),
        topic_identity_is_current=_preference_topic_identity_resolver(
            service=service,
            holder_user_id=operator_id,
        ),
        delegation_repository=delegation_repository,
    )
    if structured_resolver is not None and _provision_structured_authority:
        # The local tool cannot be advertised until its complete, factory-bound
        # authority tuple is durably active in the semantic writer's store.
        service.provision_structured_submission_authority(
            authority=structured_resolver.issued_authority(),
        )
    # A prior process can stop after atomic callback admission but before the
    # worker creates its handoff. Drain that retained operation before the
    # activation reload verifies that every active control is terminal.
    recovery_deadline = time.monotonic() + 65.0
    while True:
        if not authority_is_current():
            raise LocalLevel2AuthorityError("local Level 2 authority is unavailable")
        recovery_outcomes = service.reconcile_memory_evolution()
        if not any(outcome.retryable for outcome in recovery_outcomes):
            break
        if time.monotonic() >= recovery_deadline:
            raise RuntimeError("Hermes semantic recovery remained pending")
        time.sleep(1.0)
    # The current Bootstrap capability owns the canonical registry and the
    # installation-bound local activation target. Complete the cutover before
    # Hermes can admit a completed turn, so no source can enter a partial
    # semantic runtime.
    service.activate_observation_ledger()
    from memorii.core.semantic_ingestion.hermes_completed_turn_runtime import (
        HermesCompletedTurnRuntime,
    )
    from memorii.integrations.hermes_runtime_binding import HermesProviderRuntimeBinding

    def issue_completed_turn_ingress(
        session_id: str,
        author_id: str,
        received_at: datetime,
        origin_receipt: HermesAuthenticatedOriginReceipt | None = None,
    ) -> AuthenticatedHostIngress:
        return ingress_resolver.issue(
            SimpleNamespace(
                hook="sync_turn",
                session_id=session_id,
                user_id=author_id,
                agent_id=agent_id,
                received_at=received_at,
                upstream_origin_receipt=origin_receipt,
            )
        )

    def require_current_authority() -> None:
        if not authority_is_current():
            raise LocalLevel2AuthorityError("local Level 2 authority is unavailable")

    def revoke_current_structured_grant(grant_kind: str) -> None:
        """Revoke only the current factory-issued grant for this signed-in binding."""
        if structured_resolver is None:
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        if grant_kind not in {"source", "fact", "catalog_visibility"}:
            raise ValueError("structured grant kind is invalid")
        authority = structured_resolver.issued_authority()
        grant = {
            "source": authority.source_grant,
            "fact": authority.fact_grant,
            "catalog_visibility": authority.catalog_visibility_grant,
        }[grant_kind]
        service.revoke_structured_submission_authority_grant(
            grant_kind=grant_kind,
            grant=grant,
        )

    project_task_id = _project_task_id(
        authorization.installation_id,
        bundle.profile_digests["semantic_contract_digest"],
    )

    return HermesProviderRuntimeBinding(
        service=service,
        issue_ingress=ingress_resolver.issue,
        completed_turn_runtime=HermesCompletedTurnRuntime(
            service=service,
            installation_id=authorization.installation_id,
            issue_host_ingress=issue_completed_turn_ingress,
            scoped_read_authority=scoped_read_authority,
            require_current_authority=require_current_authority,
            project_task_id=project_task_id,
            authenticated_agent_id=agent_id,
            authenticated_author_id=operator_id,
            structured_authority_request=(
                structured_resolver.issued_authority_request() if structured_resolver is not None else None
            ),
            structured_tool_is_current=(
                (lambda: authority_is_current() and _structured_tool_is_current(hermes_home))
                if structured_resolver is not None
                else None
            ),
            structured_fact_read_authority=(
                structured_resolver.issued_read_authority if structured_resolver is not None else None
            ),
            preference_service=preference_service,
        ),
        absent_author_id=operator_id,
        revoke_structured_submission_grant=(
            revoke_current_structured_grant if structured_resolver is not None else None
        ),
    )


def revoke_local_level2_structured_grant(*, context: object, grant_kind: str) -> None:
    """Run the verified local operator action before or after grant provisioning.

    The caller supplies only a closed grant-kind selector.  Factory composition
    derives the signed-in installation, operator, agent, and exact grant tuple
    from current authority artifacts before the public service performs its
    canonical durable revoke.
    """
    binding = _build_local_level2_runtime_binding(
        context,
        _provision_structured_authority=False,
        _allow_existing_operator_binding=True,
    )
    from memorii.integrations.hermes_runtime_binding import HermesProviderRuntimeBinding

    if type(binding) is not HermesProviderRuntimeBinding:
        raise RuntimeError("Hermes local revocation binding is invalid")
    action = binding.revoke_structured_submission_grant
    if not callable(action):
        raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
    try:
        action(grant_kind)
    finally:
        runtime = binding.completed_turn_runtime
        close = getattr(runtime, "close", None) if runtime is not None else None
        if callable(close):
            close()


@dataclass(frozen=True)
class _LocalLevel2IngressEvidence:
    session_id: str
    author_id: str
    agent_id: str
    origin_lineage_evidence: AuthenticatedOriginLineageEvidence | None = None


class _LocalLevel2StructuredSubmissionResolver:
    """Issue only current local structured authority for the pinned account."""

    def __init__(
        self,
        *,
        installation_id: str,
        operator_id: str,
        agent_id: str,
        project_task_id: str,
        authority_is_current,
        structured_tool_is_current,
    ) -> None:
        self._installation_id = installation_id
        self._operator_id = operator_id
        self._agent_id = agent_id
        self._authority_is_current = authority_is_current
        self._structured_tool_is_current = structured_tool_is_current
        expected = AuthenticatedPrincipalAgent(principal_id=operator_id, agent_id=agent_id)
        catalog_scope = CatalogAuthorityScope(schema_version=1, kind="base")
        self._issued_request = StructuredSubmissionAuthorityRequest(
            authenticated=expected,
            source_grant=SourceScopeGrant(
                grant_id=_grant_id(installation_id, operator_id, agent_id, "source", f"task:{project_task_id}"),
                grant_version=1,
                source_scope=f"task:{project_task_id}",
                authenticated=expected,
            ),
            fact_grant=FactScopeGrant(
                grant_id=_grant_id(installation_id, operator_id, agent_id, "fact", f"user:{operator_id}"),
                grant_version=1,
                fact_scope=f"user:{operator_id}",
                authenticated=expected,
            ),
            catalog_visibility_grant=CatalogOwnerVisibilityGrant(
                grant_id=_grant_id(installation_id, operator_id, agent_id, "catalog_visibility", catalog_scope),
                grant_version=1,
                catalog_scope=catalog_scope,
                authenticated=expected,
                purpose="visibility_status",
            ),
        )
        self.resolver_binding_digest = sha256(
            (
                "memorii.hermes.local-level2.structured-submission-resolver.v1:"
                f"{installation_id}:{operator_id}:{agent_id}"
            ).encode()
        ).hexdigest()

    def resolve_submission_authority(
        self,
        *,
        authenticated_ingress: AuthenticatedIngressContext,
        request: StructuredSubmissionAuthorityRequest,
    ) -> ResolvedStructuredSubmissionAuthority | None:
        if not self._authority_is_current():
            return None
        if not self._structured_tool_is_current():
            return None
        expected = self._issued_request.authenticated
        if (
            request != self._issued_request
            or authenticated_ingress.delivery_principal_binding.principal_subject_id != self._operator_id
            or authenticated_ingress.authenticated_agent_id != self._agent_id
        ):
            return None
        try:
            catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base(
                expected_catalog_digest=request.expected_catalog_digest
            )
        except ValueError:
            return None
        return ResolvedStructuredSubmissionAuthority(
            authenticated=expected,
            source_grant=request.source_grant,
            fact_grant=request.fact_grant,
            catalog_visibility_grant=request.catalog_visibility_grant,
            catalog=catalog,
            provider_model_prompt_provenance_digest=(request.provider_model_prompt_provenance_digest),
        )

    def issued_authority(self) -> ResolvedStructuredSubmissionAuthority:
        """Return the exact local tuple that this resolver will accept."""
        if not self._authority_is_current() or not self._structured_tool_is_current():
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        catalog = ThreePredicateSeedCatalogAuthorityRepository().resolve_base()
        return ResolvedStructuredSubmissionAuthority(
            authenticated=self._issued_request.authenticated,
            source_grant=self._issued_request.source_grant,
            fact_grant=self._issued_request.fact_grant,
            catalog_visibility_grant=self._issued_request.catalog_visibility_grant,
            catalog=catalog,
        )

    def issued_authority_request(self) -> StructuredSubmissionAuthorityRequest:
        """Return the factory-owned request the resolver alone will attest."""
        if not self._authority_is_current() or not self._structured_tool_is_current():
            raise LocalLevel2AuthorityError("local structured tool authority is unavailable")
        return self._issued_request

    def issued_read_authority(self) -> StructuredFactReadAuthority | None:
        """Issue the current fact/catalog grant pair for one protected read."""
        if not self._authority_is_current() or not self._structured_tool_is_current():
            return None
        return StructuredFactReadAuthority(
            authenticated=self._issued_request.authenticated,
            fact_grant=self._issued_request.fact_grant,
            catalog_visibility_grant=self._issued_request.catalog_visibility_grant,
        )


class _LocalLevel2IngressResolver:
    """Translate the authenticated Hermes callback into the local trial authority."""

    def __init__(self, *, installation_id: str, operator_id: str) -> None:
        self._installation_id = installation_id
        self._operator_id = operator_id

    def issue(self, request: object) -> AuthenticatedHostIngress:
        session_id = getattr(request, "session_id", None)
        user_id = getattr(request, "user_id", None)
        received_at = getattr(request, "received_at", None)
        agent_id = getattr(request, "agent_id", None)
        hook = getattr(request, "hook", None)
        upstream_origin_receipt = getattr(request, "upstream_origin_receipt", None)
        if agent_id is None:
            agent_id = _canonical_agent_id(getattr(request, "agent_identity", None))
        if not isinstance(session_id, str) or not session_id.strip() or not isinstance(received_at, datetime):
            raise TypeError("Hermes ingress request is invalid")
        author = user_id.strip() if isinstance(user_id, str) else ""
        if author != self._operator_id:
            raise ValueError("Hermes local Level 2 operator identity is substituted")
        if not isinstance(agent_id, str) or not agent_id:
            raise TypeError("Hermes agent identity is invalid")
        origin_lineage_evidence = None
        if upstream_origin_receipt is not None:
            if (
                hook not in {"sync_turn", "delegation"}
                or not isinstance(
                    upstream_origin_receipt, HermesAuthenticatedOriginReceipt
                )
                or not upstream_origin_receipt.verify()
                or upstream_origin_receipt.author_id != author
            ):
                raise ValueError("Hermes upstream origin receipt is invalid")
            origin_lineage_evidence = AuthenticatedOriginLineageEvidence.create(
                authority_digest=sha256(
                    b"memorii.hermes.local-origin-authority.v1\0"
                    + encode_typed_value(
                        (self._installation_id, self._operator_id, agent_id)
                    )
                ).hexdigest(),
                origin_receipt_digest=sha256(
                    b"memorii.hermes.local-origin-receipt.v1\0"
                    + encode_typed_value(
                        (
                            self._installation_id,
                            self._operator_id,
                            agent_id,
                            upstream_origin_receipt.session_id,
                            upstream_origin_receipt.turn_ordinal,
                            upstream_origin_receipt.source_content_digest,
                            upstream_origin_receipt.receipt_digest,
                        )
                    )
                ).hexdigest(),
            )
        evidence = _LocalLevel2IngressEvidence(
            session_id=session_id,
            author_id=author,
            agent_id=agent_id,
            origin_lineage_evidence=origin_lineage_evidence,
        )
        return AuthenticatedHostIngress(
            provider_identity="hermes",
            principal_handle=evidence,
            session_handle=evidence,
            received_at=received_at,
        )

    def resolve(self, host_ingress: AuthenticatedHostIngress, server_time: datetime) -> AuthenticatedIngressContext:
        if (
            host_ingress.provider_identity != "hermes"
            or not isinstance(host_ingress.principal_handle, _LocalLevel2IngressEvidence)
            or host_ingress.principal_handle is not host_ingress.session_handle
            or server_time.tzinfo is None
        ):
            raise ValueError("Hermes local Level 2 ingress is invalid")
        if host_ingress.received_at.tzinfo is None:
            raise ValueError("Hermes local Level 2 ingress timestamp is invalid")
        evidence = host_ingress.principal_handle
        scopes = RequiredOutcomeScopeSet.create(
            tenant_partition_id=f"local:{self._installation_id}",
            scopes={
                f"session:{evidence.session_id}",
                f"user:{evidence.author_id}",
            },
        )
        principal = DeliveryPrincipalBinding.create(
            principal_subject_id=evidence.author_id,
            tenant_partition_id=scopes.tenant_partition_id,
            provider_identity="hermes",
        )
        provenance = sha256(f"memorii.local-level2:{self._installation_id}:{evidence.author_id}".encode()).hexdigest()
        return AuthenticatedIngressContext(
            delivery_principal_binding=principal,
            authenticated_agent_id=evidence.agent_id,
            required_outcome_scopes=scopes,
            current_authorized_scopes=scopes,
            language_declaration="en",
            language_evidence_kind="authenticated_host_declaration",
            language_evidence_trust="trusted",
            language_governance_agreement="agrees",
            semantic_egress_governance=AuthenticatedSemanticEgressGovernance(
                classification="local_level2_project_assertions",
                provider="openai",
                model="gpt-4.1-nano",
                region="operator-configured",
                retention_mode="store_false",
                training_use=False,
            ),
            semantic_source_authority=AuthenticatedSemanticSourceAuthority(
                authority_class="official",
                authenticated_provenance_class="authenticated_user",
                governing_principal_id=evidence.author_id,
                policy_revision="bootstrap-v3-local-level2",
                provenance_digest=provenance,
            ),
            semantic_source_interval=AuthenticatedSemanticSourceInterval(
                # The host-signed completion instant is the source interval
                # coordinate.  Replaying a delivery must reconstruct the same
                # Step-1 material; the current server time is only used to
                # validate this ingress call above.
                start=host_ingress.received_at,
                end=None,
                authority_basis="server_source_metadata",
                provenance_digest=provenance,
                policy_revision="bootstrap-v3-local-level2",
            ),
            origin_lineage_evidence=evidence.origin_lineage_evidence,
        )


def _canonical_agent_id(value: object) -> str:
    if value is None:
        return "memorii.hermes.agent.absent.v1"
    if isinstance(value, str):
        if not value.strip() or unicodedata.normalize("NFC", value) != value:
            raise LocalLevel2AuthorityError("Hermes agent identity is invalid")
        payload = value
    else:
        try:
            payload = json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise LocalLevel2AuthorityError("Hermes agent identity is invalid") from exc
    return "memorii:hermes:agent:" + sha256(b"memorii.hermes.agent-identity.v1\0" + payload.encode("utf-8")).hexdigest()


def _project_task_id(installation_id: str, semantic_contract_digest: str) -> str:
    return (
        "memorii:hermes:task:"
        + sha256(
            (f"memorii.hermes.project_assertions.task.v1:{installation_id}:{semantic_contract_digest}").encode()
        ).hexdigest()
    )


def _grant_id(
    installation_id: str,
    operator_id: str,
    agent_id: str,
    grant_kind: str,
    scope: str | CatalogAuthorityScope,
) -> str:
    """Derive the stable v1 grant coordinate from verified factory inputs."""
    digest = sha256(
        b"memorii.hermes.local-structured-grant.v1\0"
        + encode_typed_value(
            (
                installation_id,
                operator_id,
                agent_id,
                grant_kind,
                scope.model_dump(mode="python") if isinstance(scope, CatalogAuthorityScope) else scope,
            )
        )
    ).hexdigest()
    return f"hermes-local-structured-grant:v1:{grant_kind}:{digest}"


def _structured_tool_is_current(hermes_home: Path) -> bool:
    try:
        load_local_structured_tool_authority(hermes_home=hermes_home, now=datetime.now(UTC))
    except (OSError, TypeError, ValueError):
        return False
    return True


def _require_local_cli_context(context: object) -> str:
    """Classify the primary or explicitly delegated Hermes CLI context."""

    kind = getattr(context, "agent_context", None)
    parent = getattr(context, "parent_session_id", None)
    if getattr(context, "platform", None) != "cli" or kind not in {"primary", "delegated"}:
        raise LocalLevel2AuthorityError("local Level 2 requires Hermes CLI execution")
    if kind == "primary" and (
        getattr(context, "agent_workspace", None) != "hermes" or parent is not None
    ):
        raise LocalLevel2AuthorityError("local Level 2 primary context is invalid")
    if kind == "delegated" and (not isinstance(parent, str) or not parent.strip()):
        raise LocalLevel2AuthorityError("local Level 2 delegated context is invalid")
    return kind


def _bind_single_local_operator_context(
    *,
    storage_root: Path,
    installation_id: str,
    raw_user_id: object,
    agent_id: str,
    context_kind: str,
    allow_existing_operator_binding: bool = False,
) -> str:
    """Use raw Hermes identity only to deny multi-user reuse of one local profile."""

    raw_user = raw_user_id.strip() if isinstance(raw_user_id, str) else ""
    if raw_user_id is not None and not raw_user:
        raise LocalLevel2AuthorityError("Hermes raw user consistency value is invalid")
    binding = {
        "schema": "memorii.hermes.local-operator-context.v1",
        "installation_id": installation_id,
        "primary_agent_id": agent_id,
        "raw_user_consistency_digest": sha256(
            b"memorii.hermes.raw-user-consistency.v1\0" + raw_user.encode("utf-8")
        ).hexdigest(),
    }
    if context_kind != "primary" and not (storage_root / "local-operator-context.json").exists():
        raise LocalLevel2AuthorityError("local Level 2 primary context must initialize the profile")
    payload = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    storage_root.mkdir(parents=True, exist_ok=True)
    path = storage_root / "local-operator-context.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            existing = json.loads(path.read_bytes())
        except (OSError, TypeError, ValueError) as exc:
            raise LocalLevel2AuthorityError("local Level 2 operator context is invalid") from exc
        if (
            not isinstance(existing, dict)
            or existing.get("schema") != "memorii.hermes.local-operator-context.v1"
            or existing.get("installation_id") != installation_id
            or not isinstance(existing.get("raw_user_consistency_digest"), str)
            or not isinstance(existing.get("primary_agent_id"), str)
        ):
            raise LocalLevel2AuthorityError("local Level 2 operator context is invalid") from None
        if raw_user_id is None and allow_existing_operator_binding:
            return existing["primary_agent_id"]
        if existing["raw_user_consistency_digest"] != binding["raw_user_consistency_digest"]:
            raise LocalLevel2AuthorityError(
                "local Level 2 profile is already bound to another Hermes user context"
            ) from None
        if context_kind == "primary" and existing["primary_agent_id"] != agent_id:
            raise LocalLevel2AuthorityError("local Level 2 primary agent identity is substituted") from None
        return existing["primary_agent_id"]
    if raw_user_id is None and allow_existing_operator_binding:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        raise LocalLevel2AuthorityError("local Level 2 operator context is absent")
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return agent_id


__all__ = ["build_local_level2_runtime_binding", "revoke_local_level2_structured_grant"]
