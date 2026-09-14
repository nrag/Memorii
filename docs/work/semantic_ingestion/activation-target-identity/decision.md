# Decision: Bind Activation To A Verified Target Manifest

Status: direction approved by the user; exact contract independently approved and
promoted to docs/design/semantic_ingestion_activation_target.md.

## Recommended Choice

Use an explicit target manifest, supplied through protected host configuration,
to bind the installed writer implementation, the complete published observation
schema set and the exact ledger encoder/decoder source closure. Verify it against
the installed artifact and registry before allowing activation to drain a writer.
Its three fingerprints must come from those complete contents using specified,
domain-separated canonical preimages, not from descriptive labels or the
ObservationLedgerActivation decoder alone.

The manifest belongs to release preparation and verification. Runtime requests
cannot supply or replace it, select its source root, or choose fingerprint values.
Release assembly produces its exact unsigned bytes and signing request; the
existing configured public-key verification workflow can authenticate it when
release signing is performed. Deterministic engineering tests use isolated keys
and source/package mutation tests; producing real signed artifacts stays deferred.

## Compatibility And Cutover

- Keep existing textual writer IDs, v2 ownership manifests and serialized bytes
  unchanged before explicit activation and on historical read.
- At activation, verify the target manifest and source identities first, then
  drain and atomically publish the activation, genesis head, successor admission
  and exact successor ownership manifest. The new admission and binding carry
  the verified target writer fingerprint.
- Preserve the graph-schema fingerprint as a separate coordinate. Do not replace
  it with the observation-schema fingerprint.
- Retain the approved activation field inventory if its three fingerprints can
  completely bind the verified target. If an additional persisted coordinate is
  necessary, propose that explicit schema change during design review.
- Missing or mismatched target authority fails before drain or write. Existing
  historical reads remain available; no automatic downgrade or reactivation.

## Required Design And Proof

The bounded design must specify the finite writer artifact/source inventory,
complete schema set selection, codec/dependency closure, canonical digest recipes,
manifest grammar/version, configured trust pins, installed-runtime identity check,
resource limits, and immutable retention. Source references cannot execute code
or substitute a copied source tree for the implementation actually running.

Required discriminating tests change one writer source, schema declaration,
codec source, dependency coordinate or target pin; each must reject substitution
or change the corresponding verified identity. Label/graph-ID substitution,
caller-provided manifests, mixed targets, stale registry, incomplete closure,
wrong key and post-verification file changes must reject. Old admission/binding
bytes remain exact; target identity and successor binding agree through CAS and
restart. These are engineering proofs, not release certification.

## Alternative

Retain descriptive writer strings in activation by relaxing the SHA256 contract.
This avoids a target identity manifest but does not establish which implementation
will perform ledger writes. It would require an explicit weakening of the
activation identity guarantee and is not recommended.

Owner decision and bounded design review complete. Activation implementation
resumes under the promoted contract; see closure.json.
