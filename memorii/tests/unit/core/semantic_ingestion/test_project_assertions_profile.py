from __future__ import annotations

import memorii.core.semantic_ingestion.project_assertions_profile as profile
import pytest


def test_installed_project_assertions_bundle_is_loadable_and_content_bound() -> None:
    bundle = profile.load_project_assertions_bundle()

    assert set(bundle.profile_digests) == {
        "component_fingerprint_digest",
        "egress_policy_digest",
        "predicate_catalog_digest",
        "profile_manifest_digest",
        "prompt_schema_digest",
        "semantic_contract_digest",
    }
    assert all(len(value) == 64 for value in bundle.profile_digests.values())


def test_resource_drift_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    resources = profile._load_resources()
    resources["project_assertions.prompt.v1.json"] = b'{"text":"changed"}'
    monkeypatch.setattr(profile, "_load_resources", lambda: resources)

    with pytest.raises(profile.ProjectAssertionsProfileError, match="resource digest is invalid"):
        profile.load_project_assertions_bundle()
