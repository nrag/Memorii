"""Isolated proof host; a driver prepends frozen publication inputs.

This fixture creates an ephemeral test key. It is not a release key generator
or a production authority configuration.
"""

def main(bootstrap_configuration, facts):
    import json
    from hashlib import sha256
    from pathlib import Path
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from memorii.core.memory_evolution.observation_activation_preparation import (
        ObservationActivationPreparationInputs, deployment_configuration_from_bootstrap,
        deployment_verification_receipt_from_bootstrap,
    )
    from memorii.core.memory_evolution.observation_activation_configuration import (
        ObservationActivationTargetConfiguration, RetainedObservationActivationTargetRecord,
        resolve_verified_observation_activation_target,
    )
    from memorii.core.memory_evolution.typed_value_declarations import ProtectedDeclarationParseLimits
    from memorii.core.memory_evolution.typed_value_decoder_sources import ProtectedDecoderSourceManifestLimits
    from memorii.core.memory_evolution.typed_value_publication import (
        DecoderSourceSnapshotPin, ProtectedTypedValuePublicationLimits,
        ProtectedTypedValuePublicationPins, verify_typed_value_publication,
    )
    from memorii.core.memory_evolution.typed_value_registry_history import ProtectedTypedValueRegistryHistory
    from memorii.tools.semantic_ingestion_activation_target_release import main as release
    from memorii.tools.semantic_ingestion_offline_signing import (
        PemEd25519PrivateKeySigner, load_pem_ed25519_public_key_binding,
    )
    from memorii.tools.semantic_ingestion_signature_verifier import Ed25519SignatureVerifier

    configuration = deployment_configuration_from_bootstrap(bootstrap_configuration)
    Path(HOST_SENTINEL).touch()
    receipt = deployment_verification_receipt_from_bootstrap(facts)
    source = configuration.installation_root / "memorii/core/memory_evolution/observation_registry_sources"
    roles = tuple(path.read_bytes() for path in sorted(source.rglob("*.json"))
                  if path.name not in ("publication-manifest.json", "decoder-source-manifest.json"))
    publication = verify_typed_value_publication(
        roles, (source / "decoder-source-manifest.json").read_bytes(),
        (source / "publication-manifest.json").read_bytes(), VECTOR_BYTES,
        source_package_root=configuration.installation_root,
        limits=ProtectedTypedValuePublicationLimits(
            ProtectedDeclarationParseLimits(2_000_000, 300_000, 64),
            ProtectedDecoderSourceManifestLimits(8_000_000, 300_000, 64, 10_000, 2_000_000), 2_000_000),
        pins=ProtectedTypedValuePublicationPins(PUBLICATION_DIGEST, REGISTRY_DIGEST,
            tuple(DecoderSourceSnapshotPin(*row) for row in SNAPSHOTS), VECTOR_DIGEST),
    )
    inputs = ObservationActivationPreparationInputs(configuration, receipt, publication)
    globals()["prepared_inputs"] = lambda: inputs
    key = Ed25519PrivateKey.generate()
    domain = b"isolated-release-preparation-test-key\0"
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    digest = sha256(domain + public).hexdigest()
    output = Path(OUTPUT)
    assert release(["prepare", "--host-factory", "observation_activation_host:prepared_inputs",
        "--target-id", "isolated-release-preparation", "--signature-profile-id", "isolated-test",
        "--public-key-digest", digest, "--output-directory", str(output)]) == 0
    pem = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    binding = load_pem_ed25519_public_key_binding(pem, profile_id="isolated-test", digest_domain=domain, public_key_digest=digest)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    signature = PemEd25519PrivateKeySigner.from_pem(private_pem, binding=binding).sign_preimage((output / "target-preimage.bin").read_bytes())
    (output / "target-signature.bin").write_bytes(signature)
    (output / "public-key.pem").write_bytes(pem)
    (output / "key-domain.bin").write_bytes(domain)
    arguments = ["verify", "--manifest", str(output / "target-manifest.json"),
        "--signature", str(output / "target-signature.bin"), "--public-key", str(output / "public-key.pem"),
        "--profile-id", "isolated-test", "--public-key-digest", digest,
        "--digest-domain-file", str(output / "key-domain.bin")]
    assert release(arguments) == 0
    raw = (output / "target-manifest.json").read_bytes()
    target = resolve_verified_observation_activation_target(
        ObservationActivationTargetConfiguration(configuration, receipt, Ed25519SignatureVerifier((binding,)),
            (RetainedObservationActivationTargetRecord(raw, signature, facts.configuration_identity_digest),), sha256(raw).hexdigest()),
        ProtectedTypedValueRegistryHistory((publication,)),
    )
    (output / "target-signature.bin").write_bytes(bytes([signature[0] ^ 1]) + signature[1:])
    assert release(arguments) == 1
    (output / "target-signature.bin").write_bytes(signature)
    wrong_profile = arguments.copy()
    wrong_profile[wrong_profile.index("--profile-id") + 1] = "untrusted-profile"
    assert release(wrong_profile) == 1
    wrong_key = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    (output / "public-key.pem").write_bytes(wrong_key)
    try:
        release(arguments)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("substituted PEM key was accepted")
    (output / "public-key.pem").write_bytes(pem)
    wrong_digest = arguments.copy()
    wrong_digest[wrong_digest.index("--public-key-digest") + 1] = "0" * 64
    assert release(wrong_digest) == 1
    (output / "key-domain.bin").write_bytes(b"wrong-domain")
    try:
        release(arguments)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("substituted digest domain was accepted")
    (output / "key-domain.bin").write_bytes(domain)
    modified = json.loads(raw)
    modified["target_id"] = "different-target"
    (output / "target-manifest.json").write_text(json.dumps(modified, sort_keys=True, separators=(",", ":")))
    assert release(arguments) == 1
    (output / "target-manifest.json").write_bytes(raw)
    report = dict(status="LOCAL_REAL_WHEEL_PREPARATION_VERIFIED", distributions=len(configuration.distributions),
        installed_files=len(configuration.installed_files), package_files=len(target.manifest.package_files),
        manifest_sha256=sha256(raw).hexdigest(), environment_digest=facts.configuration_identity_digest,
        wheel_sha256=target.manifest.memorii_wheel_sha256, valid_signature_accepted=True,
        corrupt_signature_rejected=True, wrong_profile_rejected=True, wrong_public_key_rejected=True,
        wrong_digest_rejected=True, wrong_domain_rejected=True, modified_manifest_rejected=True,
        retained_target_resolved=True, production_signature=False,
        ledger_activated=False, ci_claim=False)
    (output / "proof.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0
