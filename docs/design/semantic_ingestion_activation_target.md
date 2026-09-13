# Observation Activation Target Identity

Normative target-identity contract. Approved bounded design evidence is recorded in `docs/work/semantic_ingestion/activation-target-identity/`; implementation maturity is tracked separately in the observation-ledger WorkPlan. This design does not claim that runtime activation or deployment tooling is implemented.

## Boundary and production path

The three existing `ObservationLedgerActivation` fields bind the writer, full observation schema, and ledger codec. Their inventory, legacy admission/terminal bytes, profile-3 grammar, and separate `accepted_graph_schema_fingerprint` remain unchanged; this proposal adds no activation field.

The future explicit host trigger is `ProviderMemoryService.activate_observation_ledger() -> SemanticWriterCommitBinding`. It takes no request payload and is not exposed as a provider tool. It accesses `_composed_semantic_runtime` and calls the new `AuthorizedSemanticIngestionRuntime.activate_observation_ledger()`, which obtains the current binding from its own writer and calls `SemanticIngestionAtomicStore.activate_observation_ledger(writer_binding=...)`. Ordinary ingestion, constructors, startup, and registry/target configuration never activate automatically. Missing runtime/writer/store/target raises a typed activation-unavailable error; invalid supplied target configuration raises a typed configuration error during composition, without an evidence-only fallback.

`BuiltInLocalHostSemanticIngestionCapability` gains optional `observation_activation_target_configuration`. This contains exactly a deployment configuration, bootstrap receipt, signature verifier, immutable retained-record tuple, and selected manifest SHA-256 pin. Composition selects exactly one retained record by SHA-256 of raw manifest bytes, then requires its deployment identity equals E; zero/multiple matches reject. It verifies that record and supplies the same immutable verified target context to runtime, writer and store constructors. The context retains configuration and raw inputs for revalidation before drain; a constructor cannot silently substitute another context. Absence permits existing legacy construction but makes explicit activation unavailable. Custom host builders remain trusted extension points subject to the same contract.

The atomic owner revalidates this context and predecessor binding before passing `(expected_binding, verified_target)` to writer-owned drain and activation operations. The final full-inventory CAS derives all three fingerprints from that target, never from method arguments. A successful explicit host call returns the exact successor binding; unavailable/invalid authority raises before drain; drain timeout/conflict reports its preserved drain state; a completed lost-ACK retry returns the exact existing successor. Current production methods still reject; this paragraph specifies their future implementation.

Requests, capability candidates, activation arguments, registry artifacts, and process environment cannot select targets, roots, keys, or fingerprints. The trusted host bootstrap owns immutable `DeploymentConfiguration` and `ObservationActivationTargetConfiguration`; deployer/bootstrap/process creation/immutable environment/in-process host extensions are the TCB. Filesystem evidence does not attest hostile monkey-patched or preloaded objects.

## Host bootstrap and deployment configuration

Host bootstrap runs before importing any `memorii` module. It requires Python 3.11 or later, starts a fresh process with private empty `-X pycache_prefix`, and rejects `memorii` or any `memorii.*` in `sys.modules`, package-root `.pyc`, cached Memorii bytecode in the private prefix before the first Memorii import, editable/zip installs, and `sys.path` entries that can resolve a Memorii module outside the selected distribution. The launcher creates the private empty prefix before starting Python; standard-library imports during bootstrap may populate their own entries. Installation occurs in release preparation with the protected policy below, not as a side effect of runtime startup. `-B` alone is not sufficient because it can read stale bytecode. The measured positive control confirms a fresh private prefix executes corrected same-size/same-mtime source where a normal cache executes stale code.

`DeploymentConfiguration` is a protected typed host value, not JSON and not a signed artifact. The install feasibility control (`pip --no-deps --no-compile --no-index --target`) produced 1,774 installed RECORD rows from the 1,771-file wheel, with RECORD as the only unhashed row and zero `.pyc`; this supports the no-compile/RECORD rule but does not prove a full environment. It has exactly:

```
installation_root: Path; scripts_root: Path; python_implementation: str; python_version: str; platform_tag: str;
install_policy: Literal["wheel-no-compile-v1"];
cache_policy: Literal["fresh-private-prefix-v1"];
origin_policy: Literal["selected-distribution-root-v1"]; distributions: tuple[DistributionRow, ...];
installed_files: tuple[InstalledFileRow, ...]
DistributionRow = (normalized_name, version, wheel_sha256, record_sha256,
                   top_level_roots)
InstalledFileRow = (normalized_distribution, installed_relative_path,
                    sha256, size)
```

installation_root is the protected absolute installed site root; scripts_root is its protected environment script directory. Both physical anchors are excluded from content identity; moving an identical immutable environment does not change its content identity. All strings are nonempty ASCII except platform tag; hashes are lower 64-hex; size is a nonnegative host integer (empty package files are valid). Distribution rows are sorted by normalized name; installed-file rows by `(normalized_distribution, installed_relative_path)`, comparing UTF-8 bytes. Names are normalized by lowercasing and replacing each run of `-`, `_`, or `.` with `-`, and must match `[a-z0-9]+(?:-[a-z0-9]+)*`. Names and global installed-file locators are unique; exactly one row is `memorii`. `top_level_roots` is a nonempty UTF-8-byte-sorted tuple of normalized relative paths below the site anchor, each naming an importable package directory or single module file; metadata directories are handled separately. No absolute, empty, dot/dot-dot, backslash, NUL, or duplicate root/path is accepted. The install literal requires wheel-only, offline `pip --no-deps --no-compile --no-index` installation from individually verified wheel bytes. The cache literal requires launcher-created empty private prefix, matching `sys.pycache_prefix`, and no preloaded Memorii or preexisting Memorii bytecode; the origin literal requires unique distribution roots and actual module-spec origins under those roots with no shadow selection. Unknown literals reject. Bootstrap derives implementation using `platform.python_implementation()`, exact version using `platform.python_version()`, and platform tag using `sysconfig.get_platform()`; implementation must be `CPython`. These values must equal the configuration, with configured Python version at least 3.11. It requires the complete installed distribution set to equal `distributions`, each metadata name/version and exact RECORD bytes digest to agree, and every installed regular file to appear exactly once in `installed_files` with its actual digest/size. This includes generated `INSTALLER`, `direct_url.json`, `METADATA`, and all dist-info files. RECORD alone may have an absent wheel hash, but is itself hashed/pinned by both its row and `installed_files`.

The policy accepts standard installed package roots (purelib or platlib), native extensions, and RECORD-owned entrypoint scripts under the protected scripts_root. Real required dependencies numpy and jsonschema install f2py/jsonschema scripts; rejecting all scripts would make ordinary dependency installations infeasible. Installed-file locators use exactly `site/<normalized-relative-path>` or `scripts/<normalized-relative-path>`. Resolve RECORD paths against the owning dist-info parent, then require the resulting regular file belongs to exactly one protected anchor and map it to that locator. Parent components in raw RECORD paths are permitted only through this bounded resolution; manifest/configuration locators never contain dot/dot-dot components. Symlinks, special files, overlapping anchors, duplicate ownership, unrecorded site files, headers/data outside these anchors, and arbitrary external destinations reject. Every site file and every RECORD-owned script is pinned; the launcher/interpreter and other host-owned script-directory files remain the explicitly trusted bootstrap, not distribution payload. No script is executed during verification. Thus standard native dependency wheels and their installed entrypoints are supported without permitting arbitrary record traversal. Protected positive caps are 512 distributions, 250,000 installed files, 64 GiB total bytes, and 2 GiB per file; they are bootstrap limits, never manifest-controlled numeric JSON.

Deployment preparation verifies every configured wheel SHA before performing the no-compile installation and records the resulting installed-file and RECORD pins. A separate fresh runtime bootstrap runs only after that installation; it verifies the already-installed closure above and never invokes an installer. Only after those runtime checks does it derive an immutable `DeploymentVerificationReceipt` from the configuration object and actual facts. Its fields are exactly the configuration identity digest, actual Python implementation/version/platform, exact distribution row tuple, exact installed-file tuple, and the three checked install/cache/origin literal values; it is supplied only by the trusted bootstrap. It also verifies that each imported module spec origin, when later imported, lies under its declared distribution root. Only after this does host composition import Memorii and pass configuration plus receipt inward.

Core receives only the protected configuration/receipt pair. Before drain, it requires exact configuration identity, exact receipt tuples, and rechecks selected Memorii metadata, RECORD, package-root origin, and all target package bytes; it rejects a receipt/config mismatch. It does not attempt impossible pre-import verification. The receipt is trusted host composition data, not an unforgeable Python capability; no opaque issuer token or hostile-process attestation is required. The bootstrap's trusted receipt establishes that code loaded before core verification came from the pinned environment.

## Target manifest and detached signing

`ObservationActivationTargetManifest.v1` is raw control JSON outside CTV/profile-3 and the Memorii wheel. Its parser first uses `parse_canonical_raw_json_object` for UTF-8 RFC8785/no-terminal-LF/duplicate-key/no-number intake, then applies this section's exact field grammar, rejecting unknown fields, aliases, inheritance, comments, and references. Limits, based on the packaged-wheel feasibility vector (1,771 files, 11,124,966 bytes, largest 2,001,242 bytes, 1,257 registry JSON files), are 2 MiB manifest, 64,000 nodes, depth 32, 4,096 payload rows, 32 MiB payload, and 4 MiB/file.

Its root has exactly `role, version, target_id, memorii_distribution, memorii_distribution_version, memorii_wheel_sha256, payload_inventory_digest, writer_fingerprint, observation_schema_fingerprint, ledger_codec_fingerprint, typed_value_publication_digest, typed_value_registry_digest, decoder_source_manifest_digest, signature_profile_id, public_key_digest, package_files`. Every root member except `package_files` is a JSON string. `signature_profile_id` and `memorii_distribution_version` are nonempty ASCII strings; version equals the protected selected distribution version byte-for-byte, and the signature profile together with public_key_digest must match exactly one protected key binding. Role/version are literals `observation_activation_target`/ `1`; distribution is `memorii`; target ID is ASCII `[A-Za-z0-9._/-]+`; all digest fields are lower 64-hex. `package_files` rows are exactly `relative_path, sha256, size`, with ASCII normalized paths below `memorii/`, canonical-decimal string size, no symlink/dot/dot-dot, strict UTF-8 path order, and no duplicate. They equal every regular installed payload file below `memorii/`, including package data, while excluding `__pycache__`, `.pyc`, and dist-info; any excluded payload path fails.

Preimage bytes are ASCII `memorii.observation-activation-target-manifest.v1`, exactly the single NUL byte `b"\x00"`, then exact raw manifest bytes. A detached Ed25519 signature authenticates that preimage through one protected matching key binding. Core depends only on injected `verify(profile_id, public_key_digest, preimage, signature) -> bool`, never CLI/tool imports. A thin future release CLI uses existing `Ed25519SignatureVerifier`, `Ed25519VerificationKeyBinding`, and offline-signing interfaces to prepare/verify requests. Real signing remains deferred. The signature binds deployment identity indirectly: all three activation fingerprints include E below; no separate signed deployment statement or signed index is introduced.

## Complete identity recipes

Core resolves the selected `memorii` distribution from the protected receipt; its package root is the sole root. It follows no symlinks and reads every manifest package file twice, requiring both reads, row digest/size, receipt installed-file row using its `site/` locator, and RECORD entry to agree. Define `LP(x...)` as concatenation of each byte item encoded by unsigned 8-byte big-endian length then bytes.

```
P = SHA256(LP(ASCII("memorii.observation-activation.package-payload.v1"),
  for package_files in UTF-8 path order:
    UTF8(path), ASCII(size), ASCII(sha256)))

E = SHA256(LP(ASCII("memorii.observation-activation.environment.v1"),
  UTF8(python_implementation), UTF8(python_version), UTF8(platform_tag),
  UTF8(install_policy), UTF8(cache_policy), UTF8(origin_policy), ASCII(distribution_count),
  for distributions in byte order:
    UTF8(name), UTF8(version), ASCII(wheel_sha256), ASCII(record_sha256), ASCII(top_level_root_count),
    for top_level_roots in byte order: UTF8(root),
  ASCII(installed_file_count), for installed_files in byte order:
    UTF8(distribution), UTF8(path), ASCII(size), ASCII(sha256)))
```

All counts and sizes are canonical nonnegative decimal ASCII with zero encoded as `0`. The configuration identity is E. Counts delimit nested variable-length sequences; LP alone delimits byte items. Receipt configuration identity must equal recomputed E.

All target rows must produce `P == payload_inventory_digest`; the manifest Memorii version/wheel digest equal its receipt distribution row. Full payload P and environment E deliberately overbind writer and codec; no import scanning, reflection, or code discovery occurs.

Full schema authority is existing `VerifiedTypedValuePublication`: grammar, registry, every publication-selected role, decoder-source manifest, every decoder snapshot, and every compiled registry entry. Core calls `verify_typed_value_publication` with protected publication bytes/root/limits/pins. It requires one grammar/registry role, complete declared closure, and no unknown/duplicate coordinate. Publication, registry, and decoder-manifest values must equal manifest fields. An Activation-only decoder cannot stand for codec closure.

Let entries be every compiled entry sorted lexically by UTF-8 `schema_id`, then canonical decimal `schema_version`; version has no leading zero and entry_count is exact. For each entry define D fields, in order: UTF8(schema_id), ASCII(version), ASCII(schema_fingerprint), ASCII(binding_digest), ASCII(entry_digest). C is those same five D fields immediately followed by UTF8(decoder_id), ASCII(implementation_source_digest). Then:

```
schema = SHA256(LP(ASCII("memorii.observation-activation.schema.v1"), P, E,
 publication_digest, registry_digest, decoder_source_manifest_digest,
 ASCII(entry_count), D for each entry))
codec = SHA256(LP(ASCII("memorii.observation-activation.ledger-codec.v1"), P, E,
 publication_digest, registry_digest, decoder_source_manifest_digest,
 ASCII(entry_count), C for each entry))
writer = SHA256(LP(ASCII("memorii.observation-activation.writer.v1"), P, E,
 ASCII(memorii_wheel_sha256)))
```

All digests are ASCII. Target fingerprint fields must equal recomputation. Graph schema remains a predecessor-admission coordinate, excluded from these recipes.

## Retention, drain, CAS, compatibility

Protected host configuration retains append-only records of raw manifest bytes, signature bytes, key coordinate, deployment-configuration identity, and verified triple. The key is the ordered triple. A duplicate is valid only when every retained value is byte-identical; otherwise preparation fails. This is exact host configuration history, not a release store/index. The resolver returns exactly one record.

Pre-drain validation is manifest/limits, retained-record uniqueness, signature/key, receipt/configuration, target package two-read, verified publication, identities, and predecessor/graph binding. Failure before drain has no persistent effect. Drain may persist its existing fence; a later timeout/failure leaves that state and follows recovery/retry, so it does not promise no writes. After successful drain, one CAS writes existing activation, genesis head, and successor admission/ownership manifest with exact predecessor digest/epoch, verified writer fingerprint, preserved graph schema, and three matching activation fingerprints. CAS conflict writes no successor trio. Restart acknowledgement requires exact complete trio; current reload support is not yet target binding.

Historical reads use `ProtectedTypedValueRegistryHistory` and retained host records; they never relabel old bytes. Identical target repeat returns the exact trio; different target, missing retention, partial trio, downgrade, or reactivation fails closed. Rollback is only before activation. A post-cutover successor migration is out of scope and never implicit.

## Owners and proof

New core owners: `observation_activation_target.py` (manifest, receipt/configuration revalidation, identities) and `observation_activation_configuration.py` (protected host record resolver); a standalone standard-library-only host bootstrap script at `tools/observation_activation_bootstrap.py` owns pre-import verification and receipt facts; the deployer pins that script independently as part of trusted host startup. It must not import the Memorii package to perform its checks. Core reconstructs the typed receipt from those protected host facts after import. This script and its deployment documentation are required implementation deliverables, not a host task silently deferred. Thin `tools/semantic_ingestion_activation_target_release.py` owns release preparation. `writer_admission.py` owns drain/successor, `atomic_store.py` CAS/binding, `capability.py` injection, and `provider/service.py` non-test composition. Existing publication/history/source-verifier/signing interfaces retain ownership.

Proof covers byte mutation of payload/declaration/decoder/dependency/wheel/RECORD/generated metadata/key; full closure omissions/extras/paths/symlinks/pyc/RECORD-traversal/entrypoint-scripts; copied/editable/zip/shadow roots; wrong signature/receipt/caller target; schema closure/cardinality/order/version; stale publication; inter-read mutation; same-size/same-mtime stale-pyc vector; drain recovery; CAS/restart; exact legacy reads; graph separation; and target/activation/successor agreement. CI is deterministic unit/integration and release preparation on exact artifacts, not real-signing/deployment/hostile-process certification.
