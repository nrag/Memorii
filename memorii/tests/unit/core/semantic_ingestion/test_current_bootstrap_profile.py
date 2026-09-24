"""Current-release installed free-form profile contracts."""

from __future__ import annotations

import pytest
from memorii.core.memory_evolution.bootstrap_profile import (
    BootstrapProfileArtifactPayloads,
    BootstrapProfileReleaseBuilder,
    BootstrapProfileReleaseVerifier,
    BootstrapProfileVerificationError,
)


def test_installed_current_profile_builds_and_verifies() -> None:
    release = BootstrapProfileReleaseBuilder.build()

    verified = BootstrapProfileReleaseVerifier.verify(payloads=release.payloads)

    assert verified == BootstrapProfileReleaseVerifier.verify(payloads=release.payloads)
    assert verified.artifacts.freeform_admission_policy.declared_language == "en"


@pytest.mark.parametrize(
    "field",
    ("profile_manifest", "grammar_capability_manifest", "freeform_admission_policy"),
)
def test_current_profile_rejects_every_artifact_substitution(field: str) -> None:
    release = BootstrapProfileReleaseBuilder.build()
    values = release.payloads.model_dump(mode="python")
    values[field] = b"substituted"

    with pytest.raises(BootstrapProfileVerificationError):
        BootstrapProfileReleaseVerifier.verify(
            payloads=BootstrapProfileArtifactPayloads.model_validate(values)
        )
