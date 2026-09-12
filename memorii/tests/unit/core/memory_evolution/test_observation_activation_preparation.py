from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import pytest
from memorii.core.memory_evolution.observation_activation_preparation import (
    deployment_configuration_from_bootstrap,
    deployment_verification_receipt_from_bootstrap,
)
from memorii.core.memory_evolution.observation_activation_target import deployment_configuration_identity
from memorii.tools.semantic_ingestion_activation_target_release import main


@dataclass(frozen=True)
class _Distribution:
    normalized_name: str
    version: str
    wheel_sha256: str
    record_sha256: str
    top_level_roots: tuple[str, ...]


@dataclass(frozen=True)
class _InstalledFile:
    normalized_distribution: str
    installed_relative_path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class _BootstrapConfiguration:
    installation_root: Path
    scripts_root: Path
    python_implementation: str
    python_version: str
    platform_tag: str
    install_policy: Literal["wheel-no-compile-v1"]
    cache_policy: Literal["fresh-private-prefix-v1"]
    origin_policy: Literal["selected-distribution-root-v1"]
    distributions: tuple[_Distribution, ...]
    installed_files: tuple[_InstalledFile, ...]


@dataclass(frozen=True)
class _Facts:
    configuration_identity_digest: str
    python_implementation: str
    python_version: str
    platform_tag: str
    distributions: tuple[_Distribution, ...]
    installed_files: tuple[_InstalledFile, ...]
    install_policy: Literal["wheel-no-compile-v1"]
    cache_policy: Literal["fresh-private-prefix-v1"]
    origin_policy: Literal["selected-distribution-root-v1"]


def _bootstrap_configuration() -> _BootstrapConfiguration:
    return _BootstrapConfiguration(
        Path("/protected/site"), Path("/protected/scripts"), "CPython", "3.11.9", "test-platform",
        "wheel-no-compile-v1", "fresh-private-prefix-v1", "selected-distribution-root-v1",
        (_Distribution("memorii", "1.0", "a" * 64, "b" * 64, ("memorii",)),),
        (_InstalledFile("memorii", "site/memorii/__init__.py", "c" * 64, 1),),
    )


def test_bootstrap_structural_rows_convert_to_exact_core_configuration_and_receipt() -> None:
    bootstrap = _bootstrap_configuration()
    configuration = deployment_configuration_from_bootstrap(bootstrap)
    receipt = deployment_verification_receipt_from_bootstrap(
        _Facts(
            deployment_configuration_identity(configuration), bootstrap.python_implementation, bootstrap.python_version,
            bootstrap.platform_tag, bootstrap.distributions, bootstrap.installed_files, bootstrap.install_policy,
            bootstrap.cache_policy, bootstrap.origin_policy,
        )
    )
    assert receipt.configuration_identity_digest == deployment_configuration_identity(configuration)
    assert receipt.distributions == configuration.distributions
    assert receipt.installed_files == configuration.installed_files


def test_prepare_cli_refuses_existing_output_before_loading_factory(tmp_path: Path) -> None:
    output = tmp_path / "already-exists"
    output.mkdir()
    with pytest.raises(SystemExit) as raised:
        main([
            "prepare", "--host-factory", "missing.module:factory", "--target-id", "target/one",
            "--signature-profile-id", "profile", "--public-key-digest", "d" * 64,
            "--output-directory", str(output),
        ])
    assert raised.value.code == 2
    assert not list(output.iterdir())


@pytest.mark.parametrize("dimension", ["rows", "bytes"])
@pytest.mark.parametrize("excess", [0, 1])
def test_preparation_inventory_caps_are_checked_before_io(monkeypatch: pytest.MonkeyPatch, dimension: str, excess: int) -> None:
    from memorii.core.memory_evolution import observation_activation_preparation as owner
    from memorii.core.memory_evolution.observation_activation_target import (
        InstalledFileRow,
        ObservationActivationTargetError,
    )

    configuration = deployment_configuration_from_bootstrap(_bootstrap_configuration())
    count = 4096 + excess if dimension == "rows" else 9
    rows = tuple(InstalledFileRow("memorii", f"site/memorii/f{index:04d}.py", "c" * 64,
        (4 * 1024**2 if index < 8 else excess) if dimension == "bytes" else 0) for index in range(count))
    configuration = replace(configuration, installed_files=rows)

    def reached_io(_path: Path) -> int:
        raise OSError("inventory accepted before IO")

    monkeypatch.setattr(owner, "open_canonical_source_root", reached_io)
    if excess:
        with pytest.raises(ObservationActivationTargetError, match="package_inventory_limit"):
            owner._installed_memorii_package_files(configuration)
    else:
        with pytest.raises(OSError, match="inventory accepted before IO"):
            owner._installed_memorii_package_files(configuration)
