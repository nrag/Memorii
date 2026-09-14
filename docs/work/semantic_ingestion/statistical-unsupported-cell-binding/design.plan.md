# Signed Numeric-Context Authority Boundary

- Work ID: `semantic-ingestion-statistical-unsupported-cell-binding`
- Work type: `design`
- Status: complete; approved for atomic V2 implementation
- Coordinator: root
- Revised: 2026-09-12
- Parent WorkPlan: `docs/work/semantic_ingestion/engineering-closure/implementation.plan.md`
- Baseline revision: `aa41b0d2cce5e4271e823c0950fa119c036bafc9`
- Frozen input hashes: `candidate.json`

## Problem and Requirement Ledger

SIA section 5.6 makes the signed coverage manifest the complete disposition
authority, the signed gate manifest the exact metric-gate authority, and
requires the independently reconstructed bijection before activation. The
current installed runtime accepts numeric encoding specs, alpha, gates, and
memberships in configuration, making configuration a second authority. The
first remediation still left unsupported abstention gates outside numeric
evidence and did not sign the entire context. This reconstruction closes that
boundary.

| Source | Behavioral identity | Canonical owner | Evidence state |
| --- | --- | --- | --- |
| SIA 5.6 coverage | `CapabilityCoverageManifestV2` | acceptance authority registry | specified |
| SIA 5.6 gates | `CapabilityStatisticalGateManifestV2` | acceptance authority registry | specified |
| SIA cluster/evidence rules | `CapabilitySamplingFrameManifestV2` | acceptance authority registry | specified |
| Approved baseline join | `ApprovedCapabilityBaselineV2` | acceptance authority registry | specified |
| Approval release join | `CapabilityBaselineApprovalReleaseV2` | acceptance authority registry | specified |
| Held numeric contract | `PreverifiedNumericCertificationContext` | signed-manifest verifier only | specified |
| Release join | `VerifiedNumericAuthority` | baseline/release + manifest verifier | specified |
| issuance wire | `statistical_acceptance_certificate.v2` | evaluator/receipt boundary | specified |

## Independent Approval Record

The final conformance review recorded no remaining findings from the independent specification, correctness, or test reviewers. The approved V2 release retains the established authority lifecycle fields (`release_digest`, epoch, sequence, predecessor, issue/expiry, terminal state, signer reference) in addition to every signed numeric-manifest coordinate; this preserves the existing anti-rollback and history joins during the breaking cutover.

## Signed Manifest Chain

The V2 runtime config carries only canonical-base64 bytes and trust coordinates
for the capability contract, coverage manifest, gate manifest, and sampling
frame manifest, plus `manifest_trust_policy_digest`. It contains no
`specs`, `family_alpha`, `gates`, `iid`, `clusters`, or memberships;
their presence is a closed-field rejection. Constructor-held `trust_keys`
authenticates each signed registered artifact after strict base64 decoding,
canonical JSON decoding, registered-schema validation, digest recomputation,
and Ed25519 verification. Each signer key id and trust-policy digest must match
its V2 config coordinate and the other signed artifacts.

`CapabilityCoverageManifestV2` is the SIA 5.6 closed coverage model:
`schema_version, purpose, capability_fingerprint, capability_contract_digest,
cells, manifest_digest, release_id, signing_key_id, trust_policy_digest,
signature`. It creates sorted unique `CoverageDisposition` rows. Enabled
cells produce every nonempty required metric. Explicitly unsupported cells
produce exactly one `unsupported_abstention_metric_id`, no promotion metric,
but still have a normal gate, cluster memberships, and held-out events for that
abstention gate.

`CapabilityStatisticalGateManifestV2` owns the statistical decision fields.
Its closed top-level field set is exactly `schema_version, purpose,
capability_fingerprint, capability_coverage_manifest_digest,
capability_coverage_release_id, sampling_frame_manifest_digest,
numeric_encoding_registry_digest, metric_gates, manifest_digest,
signing_key_id, trust_policy_digest, signature`. Each `metric_gates` row is
the canonical SIA 5.6 decision tuple: `coverage_cell_id, metric_id,
test_method, bound, estimand, threshold, threshold_spec_id, nominal_alpha,
nominal_alpha_spec_id, minimum_clusters, cluster_value_lower_bound,
cluster_value_upper_bound, lower_spec_id, upper_spec_id, weight_spec_id,
event_value_spec_id, iid_declared`. Its gates are the exact bijection over
both enabled metrics and unsupported abstention metrics. Those gates form the
complete Holm family; unsupported means only that promotion metric families
are prohibited, never that the abstention gate or its evidence is omitted.

`CapabilitySamplingFrameManifestV2` is separately signed and owns sampling,
cluster, strata, weighting, encoding, and member fields. Its one authoritative
closed top-level field set is exactly `schema_version, purpose,
capability_fingerprint, capability_contract_digest, coverage_manifest_digest,
coverage_release_id, sampling_frame_digest,
independent_cluster_definition_digest, strata_definition_digest,
cluster_weighting_digest, numeric_encoding_registry_digest, encoding_specs,
family_alpha, family_alpha_spec_id, gate_iid_proofs, memberships,
manifest_digest, signing_key_id, trust_policy_digest, signature`.

The gate manifest's required `sampling_frame_manifest_digest` is the one-way
chain edge; the sampling frame repeats coverage/capability/encoding joins but
does not point back at the gate digest, avoiding a self-hash cycle.
`gate_iid_proofs` is an exact one-row-per-gate map of
`(locator, iid_bernoulli_clusters_proven, proof_digest)`. Each membership is
the typed closed tuple `(locator, cluster_id, provenance_ids,
expected_event_ids, weight, lower, upper)`; it preserves multiple clusters
and events per gate, frozen nonuniform normalized weights, ranges, and
denominator membership. Gate, sampling, coverage, contract, release, and
encoding digest joins must all succeed. A sampling manifest cannot introduce a
locator, cluster, event, spec, IID assertion, alpha, or weight not anchored by
the signed chain.

This docs-only feasibility artifact validates the signed sampling-frame
*declaration*: locator membership, denominator nonemptiness, distinct declared
provenance/event identifiers, normalized weights, range/spec agreement, and
IID/gate agreement. It deliberately does not claim an observed-event bijection.
Missing, extra, duplicate, or wrong-cluster observed evidence is owned by the
later production acceptance-vector suite, where retained event observations
exist; no extra signed evidence artifact is invented here.

The registry schema owns all artifact preimages. Each uses the existing
registered-artifact digest and signature construction: canonical CTV-v1 value,
registered profile binding, length-prefixed digest domain, then the registered
signature domain/preimage with signer coordinate. This is not advisory JSON
reserialization.

## Derived Authority and Evaluation

The verifier is the sole producer of the *entire*
`PreverifiedNumericCertificationContext`: encoding specs, family alpha,
family-alpha spec id, preverified gates, IID proofs, memberships, and complete
coverage dispositions. It creates:

```
VerifiedNumericAuthority = {
  approved_baseline_artifact_digest, verified_baseline_approval_release_digest,
  capability_fingerprint, capability_contract_digest, coverage_manifest_digest,
  coverage_release_id, statistical_gate_manifest_digest,
  sampling_frame_manifest_digest, sampling_frame_digest,
  independent_cluster_definition_digest, strata_definition_digest,
  cluster_weighting_digest, numeric_encoding_registry_digest,
  unsupported_cells_digest
}
```

`unsupported_cells_digest` commits the *whole* byte-sorted disposition
projection:

```
sha256(b"memorii.acceptance.unsupported-cells.v2\x00" +
       CTV-v1(tuple(CoverageDisposition maps))).hexdigest()
```

The terminal byte is actual NUL. The complete verified authority must equal the
complete held `NumericAuthority`, including the new
`sampling_frame_manifest_digest`, before any candidate policy/evidence byte
is parsed. The candidate policy decoder then requires its specs, alpha, gates,
IID flags, memberships, and authority to equal the derived context
field-for-field; no candidate can select numeric authority.

`ApprovedCapabilityBaselineV2` and `CapabilityBaselineApprovalReleaseV2` are
also registered, signed, content-addressed artifacts. Their exact closed fields
are the `capability_baseline` and `capability_release` forms frozen in
`manifest-fixtures-v1.json`: both repeat every capability, contract, coverage,
gate, sampling-frame, cluster, strata, weighting, numeric-registry, and
unsupported-cells coordinate; the release additionally binds
`approved_baseline_artifact_digest` to the SHA-256 of the complete canonical
signed baseline bytes. The fenced authority commit selects the active V2
release by its existing active-release digest. The release selects the V2
baseline through that exact binding. Fixed V2 configuration carries neither
baseline nor release bytes and cannot select either artifact.

Production binding is:
`InstalledAcceptanceRuntime.__init__` -> registered signed-manifest verifier
-> `VerifiedNumericAuthority` and `PreverifiedNumericCertificationContext`
-> `HeldBinding` -> `AcceptanceEvaluator`. Any absent trust, signature,
digest, field, join, duplicate, ordering, or equality failure has no
certificate, receipt, or deployment authorization.

## V2 Migration and Replay

The runtime config format is `memorii.acceptance.runtime.v2`. It accepts and
emits only `statistical_acceptance_certificate.v2`; V1 policy, evidence,
config, and certificate markers reject. V1 bytes may remain retained historical
data, but no evaluator, receipt, deployment, or archival-decoder API is
promised or exposed by V2. Migration reissues the three signed manifests,
matching baseline/release, registry version, and V2 config together. No absent
field has a fallback/default.

## Proof and Attack Matrix

The independent feasibility checker reimplements the exact acceptance CTV-v1
grammar (without importing acceptance), freezes literal projection bytes and
digest, uses a fixed test Ed25519 key with real canonical manifest bytes,
digests, and signatures, and verifies primitives using `cryptography` only.
It contains at least two enabled locators, two unsupported abstention gates,
two clusters for a gate, multiple events per cluster, and nonuniform normalized
weights. It mutates signed content while retaining old digests/signatures and
rejects: disposition add/remove/reorder/flip, manifest joins/fields/signature,
gates, clusters, evidence, denominator, weight, IID proof, authority field,
and V1 marker. The docs checker remains docs-only; later installed-wheel proof
consumes a frozen vector as data.

This design makes no production, test, CI, registry, config, or CLI edit.
Parent R14 remains partial. Next action: delta review of the frozen candidate.
