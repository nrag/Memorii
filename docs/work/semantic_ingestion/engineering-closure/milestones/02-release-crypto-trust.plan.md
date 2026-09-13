# Package 2: Release Crypto And Trust

- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Status: paused (signing locally verified; parent closure blocked)
- Requirements: R03, R08, R13, R16, R19

Implement crypto/trust and release assembly; unsigned, untrusted, expired,
revoked, and test-root activation fails closed. Real production trust profiles
and signed release issuance remain deferred.

## Progress

### Ed25519 verifier slice (2026-09-06)

- Added `memorii.tools.semantic_ingestion_signature_verifier` with immutable,
  duplicate-detecting `Ed25519VerificationKeyBinding` values. A binding accepts
  only a 32-byte public key, explicit profile ID, lowercase SHA-256 digest, and
  explicit digest domain; the digest must equal `SHA-256(domain || key)`.
- `Ed25519SignatureVerifier` uses `cryptography` 50.0.1's RFC 8032
  `Ed25519PublicKey.verify` against the exact caller-provided payload bytes.
  It neither hashes nor transforms the payload and rejects unknown profile/key
  coordinates and non-64-byte signatures.
- Added `ConfiguredAcceptanceTrustResolver`. It is a production composition
  path from `RegisteredApprovalExecutor.from_resolver` through the configured
  resolver to `validate_release_candidate` and its verifier-held material.
  The default resolver remains unavailable; a candidate cannot select bindings.
- Focused tests use the architecture's test-signature-profile key digest domain
  (lines 11683-11720),
  `memorii:sia-test-ed25519-public-key:v1\\0` and the RFC 8032 empty-message
  vector. No seed or private key is present in production code.
- Evidence: from `memorii/`,
  `../.venv/bin/python -m pytest tests/unit/tools/test_semantic_ingestion_signature_verifier.py -p no:cacheprovider`
  passed 22 tests; targeted Ruff, `py_compile`, and Pyright passed. The Python 3.12.14
  environment reports `cryptography` 50.0.1.
- The canonical current-release fixture now accepts an optional test-only
  signer callback and five externally supplied key digests; its default bytes
  remain legacy deterministic fixture bytes. A five-key Ed25519 fixture signs
  the canonical preimages and succeeds through `ConfiguredAcceptanceTrustResolver`
  and `verify_release_gate`. Same-length release and lifecycle signature
  changes and a wrong release purpose reject before watermark advancement.

### Remaining package work

This slice is partial for R13. A configured successor now passes its actual
resolver-created executor after the coherent baseline publication tail is
seeded; a tampered release signature rejects before publication state changes.
The file backend opt-in is test-only. Expiry, revocation,
signer-purpose, and trust lifecycle checks remain owned by the existing release
validator and are not claimed by this adapter slice.

### Coordinator Combined Signing Check

On Python 3.12.14, from `memorii/`, the coordinator ran:

```text
../.venv/bin/python -W error -m pytest tests/integration/test_semantic_ingestion_lifecycle_signing.py tests/integration/test_semantic_ingestion_release_signing.py tests/unit/tools/test_semantic_ingestion_offline_signing.py tests/unit/tools/test_semantic_ingestion_signature_verifier.py tests/unit/tools/test_traceability_release_provenance.py -p no:cacheprovider
```

Result: 81 passed in 75.03 seconds. A preceding invocation named a nonexistent
provenance test file and collected zero tests; it was corrected to the existing
owner above. This is dirty-tree local evidence, not CI or final branch proof.

Independent test consultation identified bounded evidence improvements for
ordinary lifecycle history, same-length signature tampering at both stages and
CLI signature-index rejection. These are test actions, not demonstrated P1/P2
product defects. Demanding authorization during preparation was unsupported:
preparation does not activate or authorize a lifecycle. Existing provenance
tests already cover inactive/revoked recovery signers and post-activation genesis
downgrade, so those tests are retained rather than duplicated.

## Next Action

Assemble the release runtime configuration from independently supplied
production profile/key material; production issuance remains deferred.
