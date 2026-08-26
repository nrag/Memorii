"""Verified production authority for public semantic-ingestion composition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import NoReturn, cast

from memorii.core.memory_evolution.bootstrap_profile import (
    HostBootstrapCapability,
    HostBootstrapMaterialVerifier,
    HostVerifiedBootstrapMaterial,
)
from memorii.core.memory_evolution.ingestion_contracts import (
    AuthenticatedIngressContextResolver,
    encode_typed_value,
)

_FACTORY_SYMBOL = (
    "memorii.core.semantic_ingestion.production_authority."
    "build_verified_production_host_authority"
)
_VERIFICATION_SYMBOL = (
    "memorii.core.memory_evolution.bootstrap_profile."
    "HostBootstrapMaterialVerifier.verify"
)
_ISSUANCE_TOKEN = object()


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
    "build_verified_production_host_authority",
    "verified_production_authority_inputs",
]
