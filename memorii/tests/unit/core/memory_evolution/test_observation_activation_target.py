from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from memorii.core.memory_evolution.observation_activation_target import (
    DeploymentConfiguration,
    DistributionRow,
    InstalledFileRow,
    ObservationActivationTargetError,
    PackageFileRow,
    ProtectedObservationActivationTargetLimits,
    deployment_configuration_identity,
    derive_observation_activation_target_identity,
    manifest_preimage,
    parse_observation_activation_target_manifest,
    payload_inventory_digest,
)
from memorii.core.memory_evolution.typed_value_decoder_sources import (
    DecoderSourceManifest,
    DecoderSourceManifestFile,
    DecoderSourceSnapshot,
    VerifiedDecoderSourceFile,
    VerifiedDecoderSourceManifest,
)
from memorii.core.memory_evolution.typed_value_publication import (
    DecoderSourceSnapshotPin,
    ProtectedTypedValuePublicationPins,
    PublicationDecoderSourceSnapshot,
    TypedValuePublicationManifest,
    VerifiedTypedValuePublication,
)
from memorii.core.memory_evolution.typed_value_registry_compilation import (
    CompiledPolicyDigests,
    CompiledProfile,
    CompiledRegistryEntry,
    CompiledTypedValueRegistry,
)

_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_P = "7b1930aed6f2a2722d9dbec634e37457af855842ea03c5a9c7110eb3b3f7c925"
_E = "23e051a4cfe3ac76412ba338f0a7f8541aee9b7e6a860bd745217581f47d459d"
_SCHEMA = "487d4a16731d8ae12d3ec4b60994ef54cf41f0f8f35393652972c66657a14f48"
_CODEC = "d0acca3976fa35c58c867fac28961b6b84da877ac6bde9d4039594a096a26ea3"
_WRITER = "6ec28f21a182aac5f0a86aaaf620460b69e77e14f99a0953ef1c7537e9c1e7ae"


@pytest.mark.parametrize("scripts_root", ["/protected/site", "/protected/site/bin", "/protected"])
def test_deployment_anchors_cannot_overlap(scripts_root: str) -> None:
    with pytest.raises(ObservationActivationTargetError, match="anchors_overlap"):
        replace(_configuration(), scripts_root=Path(scripts_root))


def test_deployment_anchor_parent_traversal_is_rejected() -> None:
    with pytest.raises(ObservationActivationTargetError, match="anchor_not_canonical"):
        replace(_configuration(), scripts_root=Path("/protected/other/../site"))


def _configuration() -> DeploymentConfiguration:
    return DeploymentConfiguration(
        Path("/protected/site"),
        Path("/protected/scripts"),
        "CPython",
        "3.11.9",
        "test-platform",
        "wheel-no-compile-v1",
        "fresh-private-prefix-v1",
        "selected-distribution-root-v1",
        (
            DistributionRow("dep", "2.0", "b" * 64, "c" * 64, ("dep", "dep_extra")),
            DistributionRow("memorii", "0.1.0", "d" * 64, "e" * 64, ("memorii",)),
        ),
        (
            InstalledFileRow("dep", "site/dep/__init__.py", "f" * 64, 0),
            InstalledFileRow("memorii", "site/memorii/__init__.py", _EMPTY_SHA256, 0),
        ),
    )


def _package_files() -> tuple[PackageFileRow, ...]:
    return (
        PackageFileRow("memorii/__init__.py", _EMPTY_SHA256, 0),
        PackageFileRow("memorii/writer.py", "a" * 64, 1),
    )


def _publication() -> VerifiedTypedValuePublication:
    profile = CompiledProfile("profile", "3", "revision", "0" * 64, "1" * 64)
    policies = CompiledPolicyDigests("0" * 64, "0" * 64, "0" * 64, "0" * 64)
    entries = (
        CompiledRegistryEntry(
            profile,
            "Example",
            "2",
            "c" * 64,
            policies,
            "d" * 64,
            "example.two",
            "f" * 64,
            "0" * 64,
            "e" * 64,
            "active",
        ),
        CompiledRegistryEntry(
            profile,
            "Example",
            "10",
            "8" * 64,
            policies,
            "9" * 64,
            "example.ten",
            "b" * 64,
            "0" * 64,
            "a" * 64,
            "active",
        ),
        CompiledRegistryEntry(
            profile,
            "Example",
            "1",
            "4" * 64,
            policies,
            "5" * 64,
            "example.one",
            "7" * 64,
            "0" * 64,
            "6" * 64,
            "active",
        ),
    )
    registry = CompiledTypedValueRegistry(profile, entries, "2" * 64, ())
    snapshot = "7" * 64
    source_file = VerifiedDecoderSourceFile("example.one", "source", "decoder.py", snapshot, b"")
    decoder_sources = VerifiedDecoderSourceManifest(
        DecoderSourceManifest(
            b"{}",
            "3" * 64,
            "semantic_ingestion_typed_value",
            "3",
            (DecoderSourceManifestFile("example.one", "source", "decoder.py", snapshot),),
        ),
        (source_file,),
        (DecoderSourceSnapshot("example.one", snapshot, (source_file,)),),
    )
    manifest = TypedValuePublicationManifest(
        b"{}",
        "1" * 64,
        "semantic_ingestion_typed_value",
        "3",
        (),
        "3" * 64,
        (PublicationDecoderSourceSnapshot("example.one", snapshot),),
        "2" * 64,
    )
    pins = ProtectedTypedValuePublicationPins(
        "1" * 64, "2" * 64, (DecoderSourceSnapshotPin("example.one", snapshot),), "3" * 64
    )
    return VerifiedTypedValuePublication(registry, decoder_sources, manifest, pins, "3" * 64)


def _manifest_bytes(package_files: list[dict[str, str]] | None = None) -> bytes:
    body = {
        "role": "observation_activation_target",
        "version": "1",
        "target_id": "target/one",
        "memorii_distribution": "memorii",
        "memorii_distribution_version": "0.1.0",
        "memorii_wheel_sha256": "d" * 64,
        "payload_inventory_digest": _P,
        "writer_fingerprint": _WRITER,
        "observation_schema_fingerprint": _SCHEMA,
        "ledger_codec_fingerprint": _CODEC,
        "typed_value_publication_digest": "1" * 64,
        "typed_value_registry_digest": "2" * 64,
        "decoder_source_manifest_digest": "3" * 64,
        "signature_profile_id": "release-key-1",
        "public_key_digest": "4" * 64,
        "package_files": package_files
        if package_files is not None
        else [
            {"relative_path": "memorii/__init__.py", "sha256": _EMPTY_SHA256, "size": "0"},
            {"relative_path": "memorii/writer.py", "sha256": "a" * 64, "size": "1"},
        ],
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")


def test_identity_recipes_match_independent_literal_preimages() -> None:
    identity = derive_observation_activation_target_identity(
        _configuration(), _package_files(), _publication(), "d" * 64
    )
    assert payload_inventory_digest(_package_files()) == _P
    assert deployment_configuration_identity(_configuration()) == _E
    assert identity.payload_inventory_digest == _P
    assert identity.deployment_configuration_identity_digest == _E
    assert identity.observation_schema_fingerprint == _SCHEMA
    assert identity.ledger_codec_fingerprint == _CODEC
    assert identity.writer_fingerprint == _WRITER


def test_manifest_accepts_closed_canonical_grammar_and_preserves_raw_signature_preimage() -> None:
    raw = _manifest_bytes()
    manifest = parse_observation_activation_target_manifest(raw)
    assert manifest.package_files == _package_files()
    assert manifest_preimage(manifest) == b"memorii.observation-activation-target-manifest.v1\x00" + raw


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown",
        "number",
        "terminal_lf",
        "duplicate",
        "path",
        "size",
        "order",
        "profile_type",
        "version_literal",
        "target_id",
    ],
)
def test_manifest_rejects_schema_and_raw_json_failure_families(mutation: str) -> None:
    raw = _manifest_bytes()
    if mutation == "unknown":
        body = json.loads(raw)
        body["unknown"] = "x"
        raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    elif mutation == "number":
        raw = raw.replace(b'"size":"0"', b'"size":0', 1)
    elif mutation == "terminal_lf":
        raw += b"\n"
    elif mutation == "duplicate":
        raw = raw[:-1] + b',"role":"observation_activation_target"}'
    elif mutation == "path":
        raw = raw.replace(b"memorii/writer.py", b"memorii/../writer.py")
    elif mutation == "size":
        raw = raw.replace(b'"size":"1"', b'"size":"01"')
    elif mutation == "profile_type":
        raw = raw.replace(b'"signature_profile_id":"release-key-1"', b'"signature_profile_id":false')
    elif mutation == "version_literal":
        raw = raw.replace(b'"version":"1"', b'"version":"2"')
    elif mutation == "target_id":
        raw = raw.replace(b'"target_id":"target/one"', b'"target_id":"target one"')
    else:
        raw = _manifest_bytes(
            [
                {"relative_path": "memorii/writer.py", "sha256": "a" * 64, "size": "1"},
                {"relative_path": "memorii/__init__.py", "sha256": _EMPTY_SHA256, "size": "0"},
            ]
        )
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(raw)


def test_manifest_enforces_payload_row_byte_and_zero_boundaries() -> None:
    assert parse_observation_activation_target_manifest(_manifest_bytes(package_files=[])).package_files == ()
    one = [{"relative_path": "memorii/a.py", "sha256": "a" * 64, "size": "2"}]
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(
            _manifest_bytes(one), limits=ProtectedObservationActivationTargetLimits(maximum_package_file_bytes=1)
        )
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(
            _manifest_bytes(one), limits=ProtectedObservationActivationTargetLimits(maximum_payload_bytes=1)
        )
    two = one + [{"relative_path": "memorii/b.py", "sha256": "b" * 64, "size": "0"}]
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(
            _manifest_bytes(two), limits=ProtectedObservationActivationTargetLimits(maximum_package_files=1)
        )


def test_manifest_enforces_exact_and_over_raw_limits_before_schema() -> None:
    raw = _manifest_bytes()
    exact_limits = ProtectedObservationActivationTargetLimits(maximum_manifest_bytes=len(raw))
    assert parse_observation_activation_target_manifest(raw, limits=exact_limits).target_id == "target/one"
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(
            raw,
            limits=ProtectedObservationActivationTargetLimits(maximum_manifest_bytes=len(raw) - 1),
        )
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(
            raw, limits=ProtectedObservationActivationTargetLimits(maximum_manifest_nodes=1)
        )
    with pytest.raises(ObservationActivationTargetError):
        parse_observation_activation_target_manifest(
            raw, limits=ProtectedObservationActivationTargetLimits(maximum_manifest_depth=1)
        )


@pytest.mark.parametrize(
    "field, value",
    [
        ("python_implementation", ""),
        ("python_version", "3.11\u2603"),
        ("install_policy", "other"),
        ("installed_locator", "dep/__init__.py"),
    ],
)
def test_deployment_configuration_rejects_invalid_policy_and_locator_families(field: str, value: str) -> None:
    if field == "installed_locator":
        with pytest.raises(ObservationActivationTargetError):
            InstalledFileRow("dep", value, "f" * 64, 0)
        return
    with pytest.raises(ObservationActivationTargetError):
        if field == "python_implementation":
            DeploymentConfiguration(
                Path("/protected/site"),
                Path("/protected/scripts"),
                value,
                "3.11.9",
                "test-platform",
                "wheel-no-compile-v1",
                "fresh-private-prefix-v1",
                "selected-distribution-root-v1",
                _configuration().distributions,
                _configuration().installed_files,
            )
        elif field == "python_version":
            DeploymentConfiguration(
                Path("/protected/site"),
                Path("/protected/scripts"),
                "CPython",
                value,
                "test-platform",
                "wheel-no-compile-v1",
                "fresh-private-prefix-v1",
                "selected-distribution-root-v1",
                _configuration().distributions,
                _configuration().installed_files,
            )
        else:
            DeploymentConfiguration(
                Path("/protected/site"),
                Path("/protected/scripts"),
                "CPython",
                "3.11.9",
                "test-platform",
                value,
                "fresh-private-prefix-v1",
                "selected-distribution-root-v1",
                _configuration().distributions,
                _configuration().installed_files,
            )


def test_deployment_configuration_rejects_global_locator_and_host_capacity_violations() -> None:
    duplicate_locator = (
        InstalledFileRow("dep", "site/shared.py", "f" * 64, 0),
        InstalledFileRow("memorii", "site/shared.py", _EMPTY_SHA256, 0),
    )
    with pytest.raises(ObservationActivationTargetError, match="locator_duplicate"):
        DeploymentConfiguration(
            Path("/protected/site"),
            Path("/protected/scripts"),
            "CPython",
            "3.11.9",
            "test-platform",
            "wheel-no-compile-v1",
            "fresh-private-prefix-v1",
            "selected-distribution-root-v1",
            _configuration().distributions,
            duplicate_locator,
        )
    with pytest.raises(ObservationActivationTargetError, match="size_limit"):
        DeploymentConfiguration(
            Path("/protected/site"),
            Path("/protected/scripts"),
            "CPython",
            "3.11.9",
            "test-platform",
            "wheel-no-compile-v1",
            "fresh-private-prefix-v1",
            "selected-distribution-root-v1",
            _configuration().distributions,
            (InstalledFileRow("dep", "site/oversize.py", "f" * 64, 2 * 1024 * 1024 * 1024 + 1),),
        )
    with pytest.raises(ObservationActivationTargetError):
        InstalledFileRow("dep", "site/bool.py", "f" * 64, True)
    with pytest.raises(ObservationActivationTargetError):
        InstalledFileRow("dep", "site/snowman-\u2603.py", "f" * 64, 0)
    with pytest.raises(ObservationActivationTargetError):
        DistributionRow("dep", "2.0", "b" * 64, "c" * 64, ("snowman-\u2603",))
