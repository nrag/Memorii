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
    AuthenticatedSemanticEgressGovernance,
    AuthenticatedSemanticSourceAuthority,
    AuthenticatedSemanticSourceInterval,
    DeliveryPrincipalBinding,
    RequiredOutcomeScopeSet,
)
from memorii.core.memory_plane import MemoryPlaneService
from memorii.core.memory_plane.store import JsonlMemoryPlaneStore
from memorii.core.provider.factory import build_provider_memory_service_from_env
from memorii.core.scoped_context.authority import InProcessScopedReadAuthority
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    CurrentReleaseBootstrapV3HostMaterialBuilder,
    local_level2_bootstrap_authorization_from_sidecar,
)
from memorii.core.semantic_ingestion.project_assertions_profile import load_project_assertions_bundle
from memorii.integrations.hermes_local_authority import LocalLevel2AuthorityError, load_local_level2_authority


def build_local_level2_runtime_binding(context: object) -> object:
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
    if getattr(context, "parent_session_id", None) is not None or getattr(context, "agent_workspace", None) is not None:
        raise LocalLevel2AuthorityError("local Level 2 delegated or shared execution is unsupported")
    _bind_single_local_operator_context(
        storage_root=storage_root,
        installation_id=authorization.installation_id,
        raw_user_id=getattr(context, "user_id", None),
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
            return current_authorization == authorization and dict(current_bundle.profile_digests) == dict(
                bundle.profile_digests
            )
        except (OSError, TypeError, ValueError):
            return False

    capability, verifier = CurrentReleaseBootstrapV3HostMaterialBuilder.build_capability(
        authorization=authorization,
        now=now,
        authenticated_ingress_resolver=ingress_resolver,
        authorization_is_current=authority_is_current,
    )
    memory_plane = MemoryPlaneService(record_store=JsonlMemoryPlaneStore(storage_root / "memory-plane"))
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
        session_id: str, author_id: str, received_at: datetime
    ) -> AuthenticatedHostIngress:
        return ingress_resolver.issue(
            SimpleNamespace(session_id=session_id, user_id=author_id, agent_id=agent_id, received_at=received_at)
        )

    def require_current_authority() -> None:
        if not authority_is_current():
            raise LocalLevel2AuthorityError("local Level 2 authority is unavailable")

    project_task_id = (
        "memorii:hermes:task:"
        + sha256(
            (
                "memorii.hermes.project_assertions.task.v1:"
                f"{authorization.installation_id}:"
                f"{bundle.profile_digests['semantic_contract_digest']}"
            ).encode()
        ).hexdigest()
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
        ),
        absent_author_id=operator_id,
    )


@dataclass(frozen=True)
class _LocalLevel2IngressEvidence:
    session_id: str
    author_id: str
    agent_id: str


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
        if agent_id is None:
            agent_id = _canonical_agent_id(getattr(request, "agent_identity", None))
        if not isinstance(session_id, str) or not session_id.strip() or not isinstance(received_at, datetime):
            raise TypeError("Hermes ingress request is invalid")
        author = user_id.strip() if isinstance(user_id, str) else ""
        if author != self._operator_id:
            raise ValueError("Hermes local Level 2 operator identity is substituted")
        if not isinstance(agent_id, str) or not agent_id:
            raise TypeError("Hermes agent identity is invalid")
        evidence = _LocalLevel2IngressEvidence(session_id=session_id, author_id=author, agent_id=agent_id)
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


def _bind_single_local_operator_context(*, storage_root: Path, installation_id: str, raw_user_id: object) -> None:
    """Use raw Hermes identity only to deny multi-user reuse of one local profile."""

    raw_user = raw_user_id.strip() if isinstance(raw_user_id, str) else ""
    if raw_user_id is not None and not raw_user:
        raise LocalLevel2AuthorityError("Hermes raw user consistency value is invalid")
    binding = {
        "schema": "memorii.hermes.local-operator-context.v1",
        "installation_id": installation_id,
        "raw_user_consistency_digest": sha256(
            b"memorii.hermes.raw-user-consistency.v1\0" + raw_user.encode("utf-8")
        ).hexdigest(),
    }
    payload = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    storage_root.mkdir(parents=True, exist_ok=True)
    path = storage_root / "local-operator-context.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise LocalLevel2AuthorityError(
                "local Level 2 profile is already bound to another Hermes user context"
            ) from None
        return
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


__all__ = ["build_local_level2_runtime_binding"]
