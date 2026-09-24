from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapProfileReleaseBuilder,
    BootstrapProfileReleaseVerifier,
)
from memorii.core.memory_plane.service import MemoryPlaneService
from memorii.core.semantic_ingestion.current_bootstrap_v3_authority import (
    CurrentBootstrapV3AuthorityError,
    CurrentReleaseBootstrapV3HostMaterialBuilder,
    LocalLevel2BootstrapV3Authorization,
    VerifiedBootstrapV3ResourcePolicy,
    build_project_assertions_arbitration_policy,
)
from memorii.core.semantic_ingestion.project_assertions_profile import load_project_assertions_bundle

_NOW = datetime(2026, 9, 23, tzinfo=UTC)


def _authorization(
    *, issued_at: datetime = _NOW, expires_at: datetime = _NOW + timedelta(hours=1), **updates: object
):
    profile = BootstrapProfileReleaseVerifier.verify(
        payloads=BootstrapProfileReleaseBuilder.build().payloads
    )
    policy = VerifiedBootstrapV3ResourcePolicy.from_bundle(load_project_assertions_bundle())
    body: dict[str, object] = {
        "schema_id": "memorii.semantic_ingestion.local_level2_bootstrap_v3_authorization",
        "schema_version": 1,
        "authority_kind": "local_level2_operator",
        "execution_class": "local_level2",
        "installation_id": "installation-1",
        "hermes_home_digest": "a" * 64,
        "bootstrap_profile_verification_digest": profile.verification_digest,
        "bootstrap_manifest_digest": profile.artifacts.profile_manifest.profile_digest,
        "component_root_digest": profile.artifacts.profile_manifest.component_root_digest,
        "project_assertions_catalog_digest": policy.catalog_digest,
        "project_assertions_prompt_digest": policy.prompt_schema_digest,
        "project_assertions_output_schema_digest": policy.prompt_schema_digest,
        "project_assertions_provider_binding_digest": policy.provider_binding_digest,
        "project_assertions_egress_policy_digest": policy.egress_policy_digest,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    body.update(updates)
    return LocalLevel2BootstrapV3Authorization.create(**body)


def test_current_bootstrap_builder_verifies_one_installed_release() -> None:
    envelope = CurrentReleaseBootstrapV3HostMaterialBuilder.build(
        authorization=_authorization(), now=_NOW
    )

    assert envelope.execution_class == "local_level2"
    assert envelope.bootstrap_profile.coordinate.profile_id == "memorii.bootstrap_local_english_rule"
    assert envelope.resource_policy.catalog_digest


def test_current_bootstrap_builder_denies_installed_resource_substitution() -> None:
    authorization = _authorization(project_assertions_catalog_digest="b" * 64)

    with pytest.raises(CurrentBootstrapV3AuthorityError, match="substituted"):
        CurrentReleaseBootstrapV3HostMaterialBuilder.build(authorization=authorization, now=_NOW)


def test_current_bootstrap_builder_denies_expired_authorization() -> None:
    authorization = _authorization(issued_at=_NOW - timedelta(hours=2), expires_at=_NOW - timedelta(hours=1))

    with pytest.raises(CurrentBootstrapV3AuthorityError, match="unavailable"):
        CurrentReleaseBootstrapV3HostMaterialBuilder.build(authorization=authorization, now=_NOW)


def test_project_assertion_policy_covers_exactly_the_three_current_predicates() -> None:
    bundle = build_project_assertions_arbitration_policy(at=_NOW)

    assert tuple(rule.predicate_id for rule in bundle.trust_policy.rules) == (
        "project_deadline", "project_owner", "project_status"
    )
    assert tuple(rule.predicate_id for rule in bundle.temporal_policy.rules) == (
        "project_deadline", "project_owner", "project_status"
    )


def test_local_level2_capability_initializes_monitored_status_from_installation() -> None:
    now = datetime.now(UTC)
    capability, _ = CurrentReleaseBootstrapV3HostMaterialBuilder.build_capability(
        authorization=_authorization(issued_at=now, expires_at=now + timedelta(hours=1)),
        now=now,
        authenticated_ingress_resolver=object(),
    )
    memory_plane = MemoryPlaneService()

    runtime = capability.build_semantic_ingestion_runtime(
        memory_plane=memory_plane, now_provider=lambda: now,
        bootstrap_profile=capability.envelope.bootstrap_profile,
    )

    assert runtime is not None
    assert runtime.source_normalization_host_bundle is not None
    status_records = memory_plane.list_records(
        source_kind="semantic_ingestion_capability_status"
    )
    assert len(status_records) == 1
    assert status_records[0].content["status"]["status"] == "active"
