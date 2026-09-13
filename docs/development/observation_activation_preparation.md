# Observation Activation Preparation

Preparation creates a new offline deployment and an unsigned target. It does
not activate a ledger. The operator protects the interpreter, launcher, input
wheel hashes, explicit import roots, configuration module and host module.
Production signing can happen later with the existing PEM Ed25519 adapter or an
external signer implementing the same exact preimage contract.

1. Build the reviewed Memorii wheel and obtain its complete, version-pinned
   dependency wheels for the target Python/platform. Record each wheel SHA-256
   and its explicit import roots. Native module roots include their filename;
   namespace contributors may use a relative subtree. Do not infer release
   trust from files found in the running environment.
2. Run `python tools/observation_activation_prepare.py --destination NEW_ABSOLUTE_PATH
   --wheel WHEEL_ABSOLUTE_PATH SHA256 ROOTS` with one `--wheel` for each wheel;
   `ROOTS` is a sorted comma-separated list. The destination must not exist.
   All wheel pins are checked before the offline, no-dependency, no-bytecode
   installation. The installed metadata, RECORD ownership and complete site
   and scripts inventory are checked before emitting configuration.
3. Review and retain the printed SHA-256 pins for `deployment_configuration.py`
   and `observation_activation_bootstrap.py`. These are protected Python host
   inputs, not request JSON. Keep the prefix immutable. Failed preparation may
   leave a disposable partial prefix; retry in a new destination.
4. Provide a protected host module with `main(configuration, facts) -> int`.
   Inside that function, convert the already verified facts using
   `deployment_configuration_from_bootstrap` and
   `deployment_verification_receipt_from_bootstrap`. Supply a publication
   verified against separately reviewed registry/publication/vector pins.
   A factory returns `ObservationActivationPreparationInputs` containing those
   three typed values. Do not choose pins from runtime requests.
5. Create an empty private cache directory with mode 0700 for each invocation.
   Run the pinned launcher with `python -I -S -X pycache_prefix=PRIVATE_CACHE
   tools/observation_activation_launch.py --bootstrap PATH --bootstrap-sha256 SHA
   --configuration PATH --configuration-sha256 SHA --host PATH --host-sha256 SHA`.
   It checks the protected modules, verifies the complete deployment, installs
   the import-origin guard, and only then loads the host. Runtime never installs.
6. From the bootstrapped host, invoke the packaged
   `memorii.tools.semantic_ingestion_activation_target_release.main` with
   `prepare --host-factory MODULE:FACTORY --target-id ID
   --signature-profile-id PROFILE --public-key-digest DIGEST
   --output-directory NEW_DIRECTORY`. Retain `target-manifest.json` and
   `target-preimage.bin`. The latter contains the exact domain prefix and raw
   canonical manifest bytes to sign. Do not reserialize the manifest afterward.
7. Use `memorii.tools.semantic_ingestion_offline_signing sign-preimage --help`
   for the existing signer options. Verify with the target release tool's
   `verify --manifest PATH --signature PATH --public-key PEM --profile-id PROFILE
   --public-key-digest DIGEST --digest-domain-file PATH`. The protected key digest
   is SHA-256 of the configured key-domain bytes followed by the raw Ed25519
   public key. A successful signature check is not ledger activation authority.

The reproducible local fixture lives in
`docs/work/semantic_ingestion/observation-ledger/release-preparation/`.
`run_installed_proof.py PREPARED_DIRECTORY NEW_PROOF_DIRECTORY` exercises the
installed registry, target preparation, ephemeral test-key signing and retained
target resolver. `check_installed_rejections.py PREPARED_DIRECTORY PROOF_DIRECTORY`
tests protected-pin and installed-file tampering on that disposable installation.
It temporarily changes dependency bytes and must never target a live deployment.
The fixture creates no production private key and makes no CI or release claim.
