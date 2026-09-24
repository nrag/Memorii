"""Closed local Level 2 observation-activation target checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from memorii.core.memory_evolution import observation_activation_configuration
from memorii.core.memory_evolution.observation_activation_configuration import (
    LocalLevel2ObservationActivationTargetConfiguration,
    ObservationActivationTargetConfigurationError,
    local_level2_package_root_digest,
    resolve_verified_observation_activation_target,
    revalidate_verified_observation_activation_target,
)
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import _publication


def _configuration(root: Path, *, now: datetime) -> LocalLevel2ObservationActivationTargetConfiguration:
    return LocalLevel2ObservationActivationTargetConfiguration(
        sidecar_authorization_digest="a" * 64,
        bootstrap_profile_verification_digest="b" * 64,
        component_root_digest="c" * 64,
        resource_policy_digest="d" * 64,
        package_root=root,
        package_root_digest=local_level2_package_root_digest(root),
        typed_value_publication_digest="e" * 64,
        typed_value_registry_digest="f" * 64,
        decoder_source_manifest_digest="0" * 64,
        expires_at=now + timedelta(minutes=1),
        now_provider=lambda: now,
    )


def test_local_target_verifies_package_at_startup_and_revalidates_without_tree_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "memorii").mkdir()
    (package_root / "memorii" / "runtime.py").write_text("current = True\n")
    now = datetime(2026, 9, 23, tzinfo=UTC)
    configuration = _configuration(package_root, now=now)
    history_root = tmp_path / "history"
    history_root.mkdir()
    history = _publication(history_root, schemas=("MemoryScope",))
    configuration = replace(
        configuration,
        typed_value_publication_digest=history.publications[0].publication_manifest.publication_digest,
        typed_value_registry_digest=history.publications[0].compiled_registry.registry_digest,
        decoder_source_manifest_digest=history.publications[0].publication_manifest.decoder_source_manifest_digest,
    )
    # A substituted package fails before the immutable runtime target exists.
    (package_root / "memorii" / "runtime.py").write_text("current = False\n")
    with pytest.raises(ObservationActivationTargetConfigurationError, match="package_root_changed"):
        resolve_verified_observation_activation_target(configuration, history)

    # Re-resolving performs the full startup measurement once.  A protected
    # write must not recursively read or hash the editable package again.
    configuration = replace(
        configuration,
        package_root_digest=local_level2_package_root_digest(package_root),
    )
    target = resolve_verified_observation_activation_target(configuration, history)

    def package_tree_read_after_startup(_: Path) -> str:
        raise AssertionError("protected write must not rescan the package tree")

    monkeypatch.setattr(
        observation_activation_configuration,
        "_package_root_digest",
        package_tree_read_after_startup,
    )
    assert revalidate_verified_observation_activation_target(target, history) is target

    # The immutable registry generation is part of the target evidence.  A
    # reconstructed history must resolve a new target before it can write.
    replacement_history = ProtectedTypedValueRegistryHistory(history.publications)
    with pytest.raises(ObservationActivationTargetConfigurationError, match="target_changed"):
        revalidate_verified_observation_activation_target(target, replacement_history)


def test_local_target_rejects_expiry_and_nonlocal_configuration(tmp_path: Path) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    (package_root / "memorii").mkdir()
    now = datetime(2026, 9, 23, tzinfo=UTC)
    configuration = _configuration(package_root, now=now)
    history_root = tmp_path / "history"
    history_root.mkdir()
    history = _publication(history_root, schemas=("MemoryScope",))
    configuration = replace(
        configuration,
        typed_value_publication_digest=history.publications[0].publication_manifest.publication_digest,
        typed_value_registry_digest=history.publications[0].compiled_registry.registry_digest,
        decoder_source_manifest_digest=history.publications[0].publication_manifest.decoder_source_manifest_digest,
        expires_at=now - timedelta(seconds=1),
    )
    with pytest.raises(ObservationActivationTargetConfigurationError, match="expired"):
        resolve_verified_observation_activation_target(configuration, history)
    with pytest.raises(ObservationActivationTargetConfigurationError, match="configuration_invalid"):
        resolve_verified_observation_activation_target(object(), history)  # type: ignore[arg-type]
