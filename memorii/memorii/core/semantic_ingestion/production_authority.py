"""Verified production authority for public semantic-ingestion composition."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import NoReturn, cast

from memorii.core.memory_evolution.bootstrap_profile import (
    HostBootstrapCapability,
    HostBootstrapMaterialVerifier,
    HostVerifiedBootstrapMaterial,
)
from memorii.core.memory_evolution.capability_monitoring import (
    CapabilityAuthorizationCheckpoint,
    CapabilityEvidenceWindow,
    CapabilityEvidenceWindowProvider,
    CapabilityMonitoringPolicy,
)
from memorii.core.memory_evolution.deployment_authorization import (
    DeploymentAuthorizationArtifact,
    DeploymentAuthorizationArtifactVerifier,
    DeploymentAuthorizationCurrentTrustVerifier,
    DeploymentAuthorizationError,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContextResolver,
    encode_typed_value,
)
from memorii.core.semantic_ingestion.contracts import contract_digest

_FACTORY_SYMBOL = (
    "memorii.core.semantic_ingestion.production_authority."
    "build_verified_production_host_authority"
)
_VERIFICATION_SYMBOL = (
    "memorii.core.memory_evolution.bootstrap_profile."
    "HostBootstrapMaterialVerifier.verify"
)
_ISSUANCE_TOKEN = object()
_MONITORING_ISSUANCE_TOKEN = object()


@dataclass(frozen=True)
class ProductionAuthorityOperationToken:
    """Non-serializable identity marker for a factory-issued authority."""

    def __reduce__(self) -> NoReturn:
        raise TypeError("production authority operation tokens are not serializable")


@dataclass(frozen=True)
class ProductionAuthorityCompositionReceipt:
    """Ephemeral receipt issued only after production material verification."""

    authority_digest: str
    verified_material_digest: str
    verification_digest: str
    trust_domain: str
    factory_symbol: str
    verification_symbol: str
    _token: ProductionAuthorityOperationToken

    def __reduce__(self) -> NoReturn:
        raise TypeError("production authority receipts are not serializable")


@dataclass(frozen=True)
class VerifiedProductionHostAuthority:
    """Opaque verified inputs consumed by the public production roots only."""

    _capability: HostBootstrapCapability
    _verifier: HostBootstrapMaterialVerifier
    _material: HostVerifiedBootstrapMaterial
    _ingress_resolver: AuthenticatedIngressContextResolver
    receipt: ProductionAuthorityCompositionReceipt
    _issuance_token: object


@dataclass(frozen=True)
class VerifiedCapabilityMonitoringAuthority:
    """Signed capability-baseline authority plus its host evidence source."""

    _policy: CapabilityMonitoringPolicy
    _initial_evidence: CapabilityEvidenceWindow
    _evidence_provider: CapabilityEvidenceWindowProvider
    _deployment_artifact: DeploymentAuthorizationArtifact
    _deployment_authorization_bytes: bytes
    _current_trust_verifier: DeploymentAuthorizationCurrentTrustVerifier
    _issuance_token: object


def capability_monitoring_authority_is_current(
    authority: VerifiedCapabilityMonitoringAuthority, *, server_time: datetime
) -> bool:
    """Revalidate the retained signed deployment coordinates at each use."""
    artifact = authority._deployment_artifact
    return authority._current_trust_verifier.verify_current(
        raw=authority._deployment_authorization_bytes, server_time=server_time,
        purpose="semantic_ingestion_capability_baseline", target_kind="capability_baseline",
        target_artifact_digest=artifact.target_artifact_digest,
        capability_fingerprint=authority._policy.capability_fingerprint,
        authority_snapshot_digest=artifact.authority_snapshot_digest,
        active_epoch=artifact.active_epoch,
    ) == artifact


@contextmanager
def capability_monitoring_authority_current_use(
    authority: VerifiedCapabilityMonitoringAuthority, *, server_time: datetime
) -> Iterator[bool]:
    """Hold the host-owned revocation linearizer for one group CAS."""
    artifact = authority._deployment_artifact
    with authority._current_trust_verifier.verify_current_use(
        raw=authority._deployment_authorization_bytes,
        server_time=server_time,
        purpose="semantic_ingestion_capability_baseline",
        target_kind="capability_baseline",
        target_artifact_digest=artifact.target_artifact_digest,
        capability_fingerprint=authority._policy.capability_fingerprint,
        authority_snapshot_digest=artifact.authority_snapshot_digest,
        active_epoch=artifact.active_epoch,
    ) as current:
        yield current == artifact


def capability_monitoring_authority_checkpoint(
    authority: VerifiedCapabilityMonitoringAuthority,
) -> CapabilityAuthorizationCheckpoint:
    """Expose the complete signed deployment coordinate set for durable binding."""
    artifact = authority._deployment_artifact
    values = {
        "capability_fingerprint": authority._policy.capability_fingerprint,
        "monitoring_policy_digest": authority._policy.policy_digest,
        "deployment_authorization_digest": artifact.authorization_digest,
        "deployment_artifact_raw_digest": sha256(authority._deployment_authorization_bytes).hexdigest(),
        "target_artifact_digest": artifact.target_artifact_digest,
        "approval_release_digest": artifact.verified_capability_baseline_approval_release_digest,
        "expires_at": artifact.expires_at,
        "signer_subject_id": artifact.signer_subject_id,
        "signing_key_reference": artifact.signing_key_reference,
        "authority_snapshot_digest": artifact.authority_snapshot_digest,
        "active_epoch": artifact.active_epoch,
    }
    assert values["approval_release_digest"] is not None
    return CapabilityAuthorizationCheckpoint(
        **values,
        checkpoint_digest=contract_digest(
            b"memorii.semantic-ingestion.capability-authorization-checkpoint.v1", values
        ),
    )


def build_verified_capability_monitoring_authority(
    *,
    deployment_authorization_bytes: bytes,
    deployment_authorization_verifier: DeploymentAuthorizationArtifactVerifier,
    deployment_authorization_current_trust_verifier: DeploymentAuthorizationCurrentTrustVerifier,
    policy: CapabilityMonitoringPolicy,
    initial_evidence: CapabilityEvidenceWindow,
    evidence_provider: CapabilityEvidenceWindowProvider,
    server_time: datetime,
) -> VerifiedCapabilityMonitoringAuthority | None:
    """Bind a monitor policy to a verified signed capability-baseline release."""

    if not hasattr(evidence_provider, "load_evidence_windows"):
        return None
    try:
        policy = CapabilityMonitoringPolicy.model_validate_json(
            policy.model_dump_json()
        )
        initial_evidence = CapabilityEvidenceWindow.model_validate_json(
            initial_evidence.model_dump_json()
        )
        raw = bytes(deployment_authorization_bytes)
        artifact = deployment_authorization_verifier.verify(raw, server_time=server_time)
    except (DeploymentAuthorizationError, TypeError, ValueError):
        return None
    baseline_digest = contract_digest(
        b"memorii.semantic-ingestion.capability-monitoring-baseline.v1",
        {
            "monitoring_policy_digest": policy.policy_digest,
            "initial_evidence_window_digest": initial_evidence.evidence_window_digest,
        },
    )
    if (
        artifact.purpose != "semantic_ingestion_capability_baseline"
        or artifact.target_kind != "capability_baseline"
        or artifact.target_artifact_digest != baseline_digest
        or artifact.capability_fingerprint != policy.capability_fingerprint
        or initial_evidence.capability_fingerprint != policy.capability_fingerprint
        or initial_evidence.monitoring_policy_digest != policy.policy_digest
        or artifact.verified_capability_baseline_approval_release_digest is None
        or artifact.active_epoch != 1
    ):
        return None
    current = deployment_authorization_current_trust_verifier.verify_current(
        raw=raw, server_time=server_time,
        purpose="semantic_ingestion_capability_baseline", target_kind="capability_baseline",
        target_artifact_digest=baseline_digest,
        capability_fingerprint=policy.capability_fingerprint,
        authority_snapshot_digest=artifact.authority_snapshot_digest,
        active_epoch=artifact.active_epoch,
    )
    if current != artifact:
        return None
    return VerifiedCapabilityMonitoringAuthority(
        _policy=policy,
        _initial_evidence=initial_evidence,
        _evidence_provider=evidence_provider,
        _deployment_artifact=artifact,
        _deployment_authorization_bytes=raw,
        _current_trust_verifier=deployment_authorization_current_trust_verifier,
        _issuance_token=_MONITORING_ISSUANCE_TOKEN,
    )


def verified_capability_monitoring_authority_inputs(
    authorities: tuple[VerifiedCapabilityMonitoringAuthority, ...],
) -> tuple[
    tuple[CapabilityMonitoringPolicy, ...],
    CapabilityEvidenceWindowProvider | None,
    tuple[CapabilityEvidenceWindow, ...],
]:
    """Return verified monitor inputs and signed initialization coordinates."""

    if any(
        type(authority) is not VerifiedCapabilityMonitoringAuthority
        or authority._issuance_token is not _MONITORING_ISSUANCE_TOKEN
        for authority in authorities
    ):
        raise ValueError("verified capability monitoring authority is invalid")
    providers = {id(authority._evidence_provider) for authority in authorities}
    if len(providers) > 1:
        raise ValueError(
            "verified capability monitoring authorities use different evidence providers"
        )
    return (
        tuple(authority._policy for authority in authorities),
        authorities[0]._evidence_provider if authorities else None,
        tuple(authority._initial_evidence for authority in authorities),
    )


def build_verified_production_host_authority(
    *,
    host_bootstrap_capability: HostBootstrapCapability,
    host_bootstrap_material_verifier: HostBootstrapMaterialVerifier,
    server_time: datetime,
) -> VerifiedProductionHostAuthority | None:
    """Verify production host material once before public-root composition."""

    try:
        presentation = host_bootstrap_capability.load_bootstrap_material_presentation()
        material = (
            host_bootstrap_material_verifier.verify(
                presentation=presentation,
                required_trust_domain="production",
                server_time=server_time,
            )
            if presentation is not None
            else None
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return None
    if (
        material is None
        or material.trust_domain != "production"
        or material.release_evidence.trust_domain != "production"
    ):
        return None
    resolver = material.authenticated_ingress_resolver
    if not hasattr(resolver, "resolve"):
        return None
    material_digest = _material_digest(material)
    verification_digest = sha256(
        encode_typed_value(
            {
                "verified_material_digest": material_digest,
                "release_evidence_digest": material.release_evidence.evidence_digest,
                "trust_domain": material.trust_domain,
            }
        )
    ).hexdigest()
    authority_digest = sha256(
        encode_typed_value(
            {
                "verified_material_digest": material_digest,
                "verification_digest": verification_digest,
                "trust_domain": material.trust_domain,
            }
        )
    ).hexdigest()
    receipt = ProductionAuthorityCompositionReceipt(
        authority_digest=authority_digest,
        verified_material_digest=material_digest,
        verification_digest=verification_digest,
        trust_domain="production",
        factory_symbol=_FACTORY_SYMBOL,
        verification_symbol=_VERIFICATION_SYMBOL,
        _token=ProductionAuthorityOperationToken(),
    )
    return VerifiedProductionHostAuthority(
        _capability=host_bootstrap_capability,
        _verifier=host_bootstrap_material_verifier,
        _material=material,
        _ingress_resolver=cast(AuthenticatedIngressContextResolver, resolver),
        receipt=receipt,
        _issuance_token=_ISSUANCE_TOKEN,
    )


def verified_production_authority_inputs(
    authority: VerifiedProductionHostAuthority,
) -> tuple[
    HostBootstrapCapability,
    HostVerifiedBootstrapMaterial,
    AuthenticatedIngressContextResolver,
]:
    """Return factory-issued inputs, rejecting substituted opaque bundles."""

    if (
        type(authority) is not VerifiedProductionHostAuthority
        or authority._issuance_token is not _ISSUANCE_TOKEN
        or authority.receipt._token is None
        or authority.receipt.trust_domain != "production"
    ):
        raise ValueError("verified production host authority is invalid")
    return authority._capability, authority._material, authority._ingress_resolver


def _material_digest(material: HostVerifiedBootstrapMaterial) -> str:
    return sha256(
        encode_typed_value(
            {
                "release_metadata": material.release_metadata.model_dump(mode="python"),
                "trust_anchor": material.trust_anchor.model_dump(mode="python"),
                "release_evidence": material.release_evidence.model_dump(mode="python"),
                "profile_enabled": material.profile_enabled,
                "trust_domain": material.trust_domain,
            }
        )
    ).hexdigest()


__all__ = [
    "ProductionAuthorityCompositionReceipt",
    "ProductionAuthorityOperationToken",
    "VerifiedProductionHostAuthority",
    "VerifiedCapabilityMonitoringAuthority",
    "build_verified_capability_monitoring_authority",
    "capability_monitoring_authority_is_current",
    "capability_monitoring_authority_checkpoint",
    "build_verified_production_host_authority",
    "verified_capability_monitoring_authority_inputs",
    "verified_production_authority_inputs",
]
