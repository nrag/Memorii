"""Test-only authenticated host bootstrap authority.

The core package models the release claim but never issues it.  These fixtures
provide an opaque, keyed host verifier so tests exercise the same external
authentication boundary as production composition.
"""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from hmac import compare_digest, digest
from typing import Literal

from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapProfileReleaseMetadata,
    HostBootstrapMaterialPresentation,
    HostBootstrapMaterialVerifier,
    HostVerifiedBootstrapMaterial,
    HostVerifiedBootstrapReleaseEvidence,
)
from memorii.core.memory_evolution.ingestion_contracts import encode_typed_value

_TEST_HOST_VERIFIER_SECRET = b"memorii-semantic-ingestion-test-host-verifier-v1"


def build_test_host_verified_bootstrap_release_evidence(
    *,
    metadata: BootstrapProfileReleaseMetadata,
    external_root_digest: str,
    active_lifecycle_snapshot_digest: str,
    verified_at: datetime,
    trust_domain: Literal["production", "scenario_test"] = "production",
) -> HostVerifiedBootstrapReleaseEvidence:
    body = {
        "coordinate": metadata.coordinate.model_dump(mode="python"),
        "signed_release_digest": metadata.signed_release_digest,
        "bootstrap_anchor_digest": metadata.bootstrap_profile_trust_anchor_digest,
        "external_root_digest": external_root_digest,
        "active_lifecycle_snapshot_digest": active_lifecycle_snapshot_digest,
        "lifecycle_state": "active",
        "trust_domain": trust_domain,
        "verified_at": verified_at,
    }
    return HostVerifiedBootstrapReleaseEvidence(
        **body,
        evidence_digest=sha256(
            b"memorii.semantic_ingestion.host_verified_bootstrap_release_evidence.v1\0"
            + encode_typed_value(body)
        ).hexdigest(),
    )


def _proof_payload(material: HostVerifiedBootstrapMaterial) -> bytes:
    return encode_typed_value(
        {
            "release_metadata": material.release_metadata.model_dump(mode="python"),
            "trust_anchor": material.trust_anchor.model_dump(mode="python"),
            "artifact_payloads": material.artifact_payloads.model_dump(mode="python"),
            "release_evidence": material.release_evidence.model_dump(mode="python"),
            "profile_enabled": material.profile_enabled,
            "trust_domain": material.trust_domain,
        }
    )


def present_authenticated_host_bootstrap_material(
    material: HostVerifiedBootstrapMaterial,
) -> HostBootstrapMaterialPresentation:
    return HostBootstrapMaterialPresentation(
        material=material,
        authentication_proof=digest(_TEST_HOST_VERIFIER_SECRET, _proof_payload(material), "sha256"),
    )


class DeterministicTestHostBootstrapMaterialVerifier(HostBootstrapMaterialVerifier):
    """Fixture-only verifier that proves domain, root, lifecycle, and bytes."""

    def verify(
        self,
        *,
        presentation: HostBootstrapMaterialPresentation,
        required_trust_domain: Literal["production", "scenario_test"],
        server_time: datetime,
    ) -> HostVerifiedBootstrapMaterial | None:
        del server_time
        material = presentation.material
        if (
            material.trust_domain != required_trust_domain
            or material.release_evidence.trust_domain != required_trust_domain
            or material.release_evidence.lifecycle_state != "active"
            or not material.release_evidence.external_root_digest
            or not material.release_evidence.active_lifecycle_snapshot_digest
            or not isinstance(presentation.authentication_proof, bytes)
        ):
            return None
        expected = digest(_TEST_HOST_VERIFIER_SECRET, _proof_payload(material), "sha256")
        if not compare_digest(expected, presentation.authentication_proof):
            return None
        return material
