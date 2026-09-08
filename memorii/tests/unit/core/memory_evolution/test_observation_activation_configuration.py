from __future__ import annotations

import base64
import csv
import importlib.metadata
import io
import json
import platform
import sysconfig
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import memorii
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from memorii.core.memory_evolution import observation_activation_package as package_verifier
from memorii.core.memory_evolution.observation_activation_configuration import (
    ObservationActivationTargetConfiguration,
    ObservationActivationTargetConfigurationError,
    RetainedObservationActivationTargetRecord,
    _select_record,
    _verify_receipt,
    resolve_verified_observation_activation_target,
)
from memorii.core.memory_evolution.observation_activation_target import (
    DeploymentConfiguration,
    DeploymentVerificationReceipt,
    DistributionRow,
    InstalledFileRow,
    PackageFileRow,
    deployment_configuration_identity,
    derive_observation_activation_target_identity,
    parse_observation_activation_target_manifest,
)
from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
from memorii.tools.semantic_ingestion_signature_verifier import (
    Ed25519SignatureVerifier,
    Ed25519VerificationKeyBinding,
)
from tests.unit.core.memory_evolution.test_typed_value_artifact_integrity import _publication


class _Verifier:
    def verify(self, profile_id: str, public_key_digest: str, payload: bytes, signature: bytes) -> bool:
        return profile_id == "test-key" and public_key_digest == "4" * 64 and payload and signature == b"s" * 64


def _deployment() -> DeploymentConfiguration:
    return DeploymentConfiguration(
        Path("/protected/site"),
        Path("/protected/scripts"),
        "CPython",
        "3.11.9",
        "test-platform",
        "wheel-no-compile-v1",
        "fresh-private-prefix-v1",
        "selected-distribution-root-v1",
        (DistributionRow("memorii", "0.1.0", "d" * 64, "e" * 64, ("memorii",)),),
        (),
    )


def _receipt(deployment: DeploymentConfiguration) -> DeploymentVerificationReceipt:
    return DeploymentVerificationReceipt(
        deployment_configuration_identity(deployment),
        deployment.python_implementation,
        deployment.python_version,
        deployment.platform_tag,
        deployment.distributions,
        deployment.installed_files,
        deployment.install_policy,
        deployment.cache_policy,
        deployment.origin_policy,
    )


def _manifest() -> bytes:
    return json.dumps(
        {
            "role": "observation_activation_target",
            "version": "1",
            "target_id": "target/one",
            "memorii_distribution": "memorii",
            "memorii_distribution_version": "0.1.0",
            "memorii_wheel_sha256": "d" * 64,
            "payload_inventory_digest": "1" * 64,
            "writer_fingerprint": "2" * 64,
            "observation_schema_fingerprint": "3" * 64,
            "ledger_codec_fingerprint": "4" * 64,
            "typed_value_publication_digest": "5" * 64,
            "typed_value_registry_digest": "6" * 64,
            "decoder_source_manifest_digest": "7" * 64,
            "signature_profile_id": "test-key",
            "public_key_digest": "4" * 64,
            "package_files": [],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _configuration(
    records: tuple[RetainedObservationActivationTargetRecord, ...],
) -> ObservationActivationTargetConfiguration:
    deployment = _deployment()
    return ObservationActivationTargetConfiguration(
        deployment,
        _receipt(deployment),
        _Verifier(),
        records,
        sha256(records[0].raw_manifest).hexdigest(),
    )


def test_retained_selection_accepts_exact_duplicate_and_rejects_conflicting_duplicate() -> None:
    raw = _manifest()
    record = RetainedObservationActivationTargetRecord(raw, b"s" * 64, deployment_configuration_identity(_deployment()))
    selected, manifest = _select_record(_configuration((record, record)))
    assert selected == record
    assert manifest.target_id == "target/one"
    conflicting = RetainedObservationActivationTargetRecord(
        raw, b"d" * 64, deployment_configuration_identity(_deployment())
    )
    with pytest.raises(ObservationActivationTargetConfigurationError, match="retained_conflict"):
        _select_record(_configuration((record, conflicting)))


def test_receipt_join_rejects_changed_configuration_tuple() -> None:
    deployment = _deployment()
    receipt = _receipt(deployment)
    changed = DeploymentVerificationReceipt(
        receipt.configuration_identity_digest,
        receipt.python_implementation,
        receipt.python_version,
        receipt.platform_tag,
        receipt.distributions,
        (InstalledFileRow("memorii", "site/memorii/__init__.py", "0" * 64, 0),),
        receipt.install_policy,
        receipt.cache_policy,
        receipt.origin_policy,
    )
    with pytest.raises(ObservationActivationTargetConfigurationError, match="receipt_mismatch"):
        _verify_receipt(deployment, changed)


def _signed_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history: ProtectedTypedValueRegistryHistory | None = None,
):
    """Isolate host import metadata; use real file, publication and crypto owners."""
    site = tmp_path / "site"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (site / "memorii").mkdir(parents=True)
    metadata_dir = site / "memorii-0.1.0.dist-info"
    metadata_dir.mkdir()
    contents = {
        "memorii/__init__.py": b"# isolated package fixture\n",
        "memorii/empty.py": b"",
        "memorii-0.1.0.dist-info/METADATA": b"Name: memorii\nVersion: 0.1.0\n",
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for path, raw in sorted(contents.items()):
        (site / path).write_bytes(raw)
        digest = base64.urlsafe_b64encode(sha256(raw).digest()).decode().rstrip("=")
        writer.writerow((path, f"sha256={digest}", str(len(raw))))
    record_path = "memorii-0.1.0.dist-info/RECORD"
    writer.writerow((record_path, "", ""))
    contents[record_path] = buffer.getvalue().encode()
    (site / record_path).write_bytes(contents[record_path])
    deployment = DeploymentConfiguration(
        site,
        scripts,
        platform.python_implementation(),
        platform.python_version(),
        sysconfig.get_platform(),
        "wheel-no-compile-v1",
        "fresh-private-prefix-v1",
        "selected-distribution-root-v1",
        (DistributionRow("memorii", "0.1.0", "d" * 64, sha256(contents[record_path]).hexdigest(), ("memorii",)),),
        tuple(
            InstalledFileRow("memorii", f"site/{path}", sha256(raw).hexdigest(), len(raw))
            for path, raw in sorted(contents.items())
        ),
    )
    distribution = importlib.metadata.PathDistribution(metadata_dir)
    original_lookup = importlib.metadata.distribution
    monkeypatch.setattr(
        importlib.metadata, "distribution", lambda name: distribution if name == "memorii" else original_lookup(name)
    )
    monkeypatch.setattr(memorii, "__file__", str(site / "memorii/__init__.py"))
    publication_dir = tmp_path / "publication"
    publication_dir.mkdir()
    if history is None:
        history = _publication(publication_dir, schemas=("MemoryScope",))
    publication = history.publications[0]
    rows = tuple(
        PackageFileRow(path, sha256(raw).hexdigest(), len(raw))
        for path, raw in sorted(contents.items())
        if path.startswith("memorii/")
    )
    identity = derive_observation_activation_target_identity(deployment, rows, publication, "d" * 64)
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes_raw()
    key_digest = sha256(b"target-test-key\0" + public).hexdigest()
    verifier = Ed25519SignatureVerifier(
        (Ed25519VerificationKeyBinding("isolated-key", public, key_digest, b"target-test-key\0"),)
    )
    body = {
        "role": "observation_activation_target",
        "version": "1",
        "target_id": "isolated-target",
        "memorii_distribution": "memorii",
        "memorii_distribution_version": "0.1.0",
        "memorii_wheel_sha256": "d" * 64,
        "payload_inventory_digest": identity.payload_inventory_digest,
        "writer_fingerprint": identity.writer_fingerprint,
        "observation_schema_fingerprint": identity.observation_schema_fingerprint,
        "ledger_codec_fingerprint": identity.ledger_codec_fingerprint,
        "typed_value_publication_digest": publication.publication_manifest.publication_digest,
        "typed_value_registry_digest": publication.compiled_registry.registry_digest,
        "decoder_source_manifest_digest": publication.publication_manifest.decoder_source_manifest_digest,
        "signature_profile_id": "isolated-key",
        "public_key_digest": key_digest,
        "package_files": [
            {"relative_path": row.relative_path, "sha256": row.sha256, "size": str(row.size)} for row in rows
        ],
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    record = RetainedObservationActivationTargetRecord(
        raw,
        key.sign(b"memorii.observation-activation-target-manifest.v1\0" + raw),
        deployment_configuration_identity(deployment),
    )
    configuration = ObservationActivationTargetConfiguration(
        deployment, _receipt(deployment), verifier, (record,), sha256(raw).hexdigest()
    )
    return configuration, history, key


def _resign(configuration, key, **changes):
    body = json.loads(configuration.retained_records[0].raw_manifest)
    body.update(changes)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    record = replace(
        configuration.retained_records[0],
        raw_manifest=raw,
        signature=key.sign(b"memorii.observation-activation-target-manifest.v1\0" + raw),
    )
    return replace(configuration, retained_records=(record,), selected_manifest_sha256=sha256(raw).hexdigest())


def test_real_signature_publication_and_package_reach_verified_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration, history, _ = _signed_package(tmp_path, monkeypatch)
    target = resolve_verified_observation_activation_target(configuration, history)
    assert target.configuration is configuration
    assert target.publication is history.publications[0]
    assert target.identity.writer_fingerprint == target.manifest.writer_fingerprint
    assert any(row.size == 0 for row in target.manifest.package_files)


@pytest.mark.parametrize(
    "field,value",
    [
        ("memorii_distribution_version", "9.9"),
        ("memorii_wheel_sha256", "0" * 64),
        ("writer_fingerprint", "0" * 64),
        ("observation_schema_fingerprint", "0" * 64),
        ("ledger_codec_fingerprint", "0" * 64),
        ("typed_value_publication_digest", "0" * 64),
        ("signature_profile_id", "other-key"),
        ("public_key_digest", "0" * 64),
    ],
)
def test_signed_target_substitution_rejects_at_real_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    configuration, history, key = _signed_package(tmp_path, monkeypatch)
    with pytest.raises(ObservationActivationTargetConfigurationError):
        resolve_verified_observation_activation_target(_resign(configuration, key, **{field: value}), history)


@pytest.mark.parametrize("mutation", ["extra", "missing", "changed", "symlink", "record", "metadata", "root"])
def test_real_package_mutations_reject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    configuration, history, _ = _signed_package(tmp_path, monkeypatch)
    site = configuration.deployment_configuration.installation_root
    file = site / "memorii/empty.py"
    if mutation == "extra":
        (site / "memorii/extra.py").write_bytes(b"")
    elif mutation == "missing":
        file.unlink()
    elif mutation == "changed":
        file.write_bytes(b"changed")
    elif mutation == "symlink":
        file.unlink()
        file.symlink_to(site / "memorii/__init__.py")
    elif mutation == "record":
        (site / "memorii-0.1.0.dist-info/RECORD").write_bytes(b"invalid")
    elif mutation == "metadata":
        (site / "memorii-0.1.0.dist-info/METADATA").write_bytes(b"Name: other\nVersion: 0.1.0\n")
    else:
        monkeypatch.setattr(memorii, "__file__", str(tmp_path / "copy/memorii/__init__.py"))
    with pytest.raises(ObservationActivationTargetConfigurationError):
        resolve_verified_observation_activation_target(configuration, history)


def test_retained_fingerprint_triplet_cannot_select_different_raw_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration, history, key = _signed_package(tmp_path, monkeypatch)
    altered = _resign(configuration, key, target_id="different-label")
    conflicting = replace(configuration, retained_records=configuration.retained_records + altered.retained_records)
    with pytest.raises(ObservationActivationTargetConfigurationError, match="retained_conflict"):
        resolve_verified_observation_activation_target(conflicting, history)


def test_inter_read_mutation_rejects_without_bypassing_file_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration, history, _ = _signed_package(tmp_path, monkeypatch)
    read = package_verifier._read_whole_file
    mutated = False

    def mutate(descriptor, path, limit):
        nonlocal mutated
        raw = read(descriptor, path, limit)
        if path == "memorii/empty.py" and not mutated:
            mutated = True
            (configuration.deployment_configuration.installation_root / path).write_bytes(b"changed")
        return raw

    monkeypatch.setattr(package_verifier, "_read_whole_file", mutate)
    with pytest.raises(ObservationActivationTargetConfigurationError):
        resolve_verified_observation_activation_target(configuration, history)
    assert mutated


@pytest.mark.parametrize("mutation", ["signature", "selection", "receipt"])
def test_protected_authority_mutations_reject(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str) -> None:
    configuration, history, _ = _signed_package(tmp_path, monkeypatch)
    if mutation == "signature":
        record = configuration.retained_records[0]
        signature = bytes([record.signature[0] ^ 1]) + record.signature[1:]
        configuration = replace(configuration, retained_records=(replace(record, signature=signature),))
    elif mutation == "selection":
        configuration = replace(configuration, selected_manifest_sha256="0" * 64)
    else:
        configuration = replace(
            configuration,
            deployment_verification_receipt=replace(
                configuration.deployment_verification_receipt, configuration_identity_digest="0" * 64
            ),
        )
    with pytest.raises(ObservationActivationTargetConfigurationError):
        resolve_verified_observation_activation_target(configuration, history)


def test_rebound_record_digest_cannot_hide_missing_payload_membership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configuration, history, key = _signed_package(tmp_path, monkeypatch)
    deployment = configuration.deployment_configuration
    record_path = deployment.installation_root / "memorii-0.1.0.dist-info/RECORD"
    raw = (
        b"\n".join(line for line in record_path.read_bytes().splitlines() if not line.startswith(b"memorii/empty.py,"))
        + b"\n"
    )
    record_path.write_bytes(raw)
    record_digest = sha256(raw).hexdigest()
    deployment = replace(
        deployment,
        distributions=(replace(deployment.distributions[0], record_sha256=record_digest),),
        installed_files=tuple(
            replace(row, sha256=record_digest, size=len(raw))
            if row.installed_relative_path.endswith(".dist-info/RECORD")
            else row
            for row in deployment.installed_files
        ),
    )
    manifest = parse_observation_activation_target_manifest(configuration.retained_records[0].raw_manifest)
    identity = derive_observation_activation_target_identity(
        deployment, manifest.package_files, history.publications[0], manifest.memorii_wheel_sha256
    )
    configuration = replace(
        configuration,
        deployment_configuration=deployment,
        deployment_verification_receipt=_receipt(deployment),
        retained_records=(
            replace(
                configuration.retained_records[0],
                deployment_configuration_identity_digest=deployment_configuration_identity(deployment),
            ),
        ),
    )
    configuration = _resign(
        configuration,
        key,
        writer_fingerprint=identity.writer_fingerprint,
        observation_schema_fingerprint=identity.observation_schema_fingerprint,
        ledger_codec_fingerprint=identity.ledger_codec_fingerprint,
    )
    with pytest.raises(ObservationActivationTargetConfigurationError) as failure:
        resolve_verified_observation_activation_target(configuration, history)
    assert isinstance(failure.value.__cause__, package_verifier.ObservationActivationPackageError)
    assert "record_membership_mismatch" in str(failure.value.__cause__)


def test_original_site_anchor_symlink_is_not_resolved_away(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configuration, history, _ = _signed_package(tmp_path, monkeypatch)
    alias = tmp_path / "site-alias"
    alias.symlink_to(configuration.deployment_configuration.installation_root, target_is_directory=True)
    deployment = replace(configuration.deployment_configuration, installation_root=alias)
    configuration = replace(configuration, deployment_configuration=deployment)
    monkeypatch.setattr(memorii, "__file__", str(alias / "memorii/__init__.py"))
    distribution = importlib.metadata.PathDistribution(alias / "memorii-0.1.0.dist-info")
    monkeypatch.setattr(importlib.metadata, "distribution", lambda _: distribution)
    with pytest.raises(ObservationActivationTargetConfigurationError):
        resolve_verified_observation_activation_target(configuration, history)


def test_scripts_anchor_cannot_alias_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configuration, history, _ = _signed_package(tmp_path, monkeypatch)
    scripts = configuration.deployment_configuration.scripts_root
    scripts.rmdir()
    scripts.symlink_to(configuration.deployment_configuration.installation_root, target_is_directory=True)
    with pytest.raises(ObservationActivationTargetConfigurationError):
        resolve_verified_observation_activation_target(configuration, history)
