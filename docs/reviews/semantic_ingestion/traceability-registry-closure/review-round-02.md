# Semantic Ingestion Traceability Registry Closure Review, Round 02

## Review Metadata

- Review date: 2026-07-27
- Review mode: fresh full review of revision 1
- Repository revision:
  `237053aef26fae2df7e6b44144e61a1b780bf7ad`
- Design baseline:
  `d8612a5defb15770a56516563fcf5a663cb6adbbed62c62bf46693ef6ac4eb60`
- Registry baseline:
  `e134cf123582838d12ae65b7d80c135f7ff7b91a6636785ba0bbc0e2b3f1467b`
- Reviewers: new `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` instances
- Revisions used before this review: 1 of 3

The reviewers read the complete revised design and registry source package
without prior review reports or WorkPlan conclusions. The coordinator
reproduced the admitted findings and separated design defects from missing
implementation of the proposed target.

## Validated Findings

All four findings have product priority `Not applicable` and design disposition
`blocks_approval`. They concern the completeness and authority of the
acceptance design; they do not demonstrate broken product behavior.

### TRC-R2-001: Eleven parser-emitted headings have no registry default

- Requirements: SIA-R03
- Confidence: high

The design requires one explicit default for every Sections 1-5 heading emitted
by the closed parser and forbids inheritance or catch-all rules. The registry
contains 133 direct numeric paths. The parser also emits 11 unnumbered headings
inside Sections 1-5: `Provider lifecycle compatibility`, Gates A through G, and
the three revision failure-pattern headings. Those units cannot resolve to a
numeric-path default.

Completion requires stable identities and explicit mappings for all 144 emitted
headings, with independent exact-set comparison and a one-missing-heading
mutation.

### TRC-R2-002: The checked-in registry violates its canonical-byte contract

- Requirements: SIA-R03
- Confidence: high

The design requires recursively Unicode-sorted object keys and no insignificant
whitespace. The checked-in registry is pretty-printed, begins with non-lexical
root key order, and contains additional nested key-order violations. Its raw
bytes therefore cannot be both the normative source package and the canonical
bytes used for source identity.

Completion requires one unambiguous canonicalizer, canonical checked-in bytes,
a newly frozen registry digest/source identity, and exact-byte tests rejecting
whitespace, CRLF, duplicate-key, and object-key-order mutations. Array order
remains semantically significant as already specified.

### TRC-R2-003: Test-evidence groups are unresolved labels

- Requirements: SIA-R03 and SIA-R13
- Confidence: high

The registry binds requirements to strings such as
`semantic-ingestion-r03`, but contains no closed, content-loadable test-group
root defining registered commands, selected test IDs, runner-report schemas,
runner requirements, or artifact/result policy. The release therefore cannot
bind the executable meaning of a test group, and an implementer or evidence
issuer must invent it.

Completion requires a canonical `test_evidence_groups` root with complete
instances and a digest in the signed release. Every requirement binding must
resolve exactly once. Independent mutations of group ID, command, selection,
report schema, runner policy, and requirement-to-group binding must invalidate
the gate.

### TRC-R2-004: Initial trust bootstrap is circular

- Requirements: SIA-R03 and SIA-R13
- Confidence: high

The proposed release identifies a trust-snapshot digest and is valid only when
its issuer is authorized by that snapshot. The external-decision row supplies
the release and snapshot together but names no independently authenticated
bootstrap root or verification coordinate. A malicious initial release can
therefore bring a snapshot that authorizes its own signer.

Completion requires the external-decision artifact to identify a separately
authenticated bootstrap trust anchor, purpose, verification profile, and
rotation/lifecycle rule. The verifier must authenticate the initial release
against that anchor before consulting release-bound reviewer/issuer snapshots.
Tests must reject self-authorization, substituted or wrong-purpose roots,
revoked/compromised roots, and rollback or replay across root rotation.

## Rejected Or Deferred Observations

- The current untracked extractor, checker, evidence helper, and tests do not
  yet implement revision 1. That is expected implementation work against a
  proposed design, not a new design finding. These files remain unchanged.
- Current provider-compatibility test exhaustiveness is unrelated to TRC-001
  and TRC-002 and is outside this frozen design-revision scope.
- Resolving `SIA-ED-TRACEABILITY-001` with actual identities, keys, and a signed
  active release remains external acceptance work. Defining a non-circular
  bootstrap contract is internal design work and is admitted above.

## Verified Positives

- The design and registry hashes match the frozen revision 1 baseline.
- All 133 direct numeric heading paths have exactly one registry default.
- All 23 SIA requirements have explicit requirement bindings.
- All 18 explicit SIA-I anchors are present.
- The overrides root is explicitly empty.
- The fourth external-decision row correctly avoids inventing external
  identities and keys.
- The design explicitly rejects arbitrary signed success-shaped bytes.

## Disposition

**Not approved.** Revision 2 is authorized for exactly TRC-R2-001 through
TRC-R2-004. No implementation changes or unrelated design corrections are
included.
