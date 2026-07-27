# Design Review: Semantic Ingestion Internal Closure, Round 02

## Review Metadata

- Review ID: `semantic-ingestion-internal-closure-round-02`
- Review mode: `full`
- Review outcome: `Changes required; external decisions remain blocked`
- Design baseline SHA-256:
  `4cd6775a3d14daf4760a8476584d5964213dad40f1d67b0b905e37c69dd59fc5`
- Design size: 13,651 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation

## Executive Assessment

Revision 01 closes SIC-001 through SIC-005. The correctness reviewer found no
remaining internal product defect. The spec and test reviewers independently
identified the same traceability boundary defect, and the test reviewer found
one additional typed-value serialization defect. Direct inspection confirms
both findings.

The frozen round-02 inventory is one P2 finding and one `Not applicable`
design-governance finding with `changes_required` disposition. No P1 finding
remains. The three registered external decisions remain separate and unchanged.

## Confirmed Internal Findings

### SIC-006: Digest-bearing contracts lack one canonical typed-value profile

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: serialization, replay, and cross-process compatibility
- Requirements: SIA-R01, SIA-R04, SIA-R10, SIA-R12, SIA-R13, SIA-R21,
  SIA-R22, and SIA-R23
- Evidence: Section 3.15.1 requires SHA-256 over RFC 8785 canonical JSON for
  all owned ingestion types, while those contracts contain `datetime`, `bytes`,
  `timedelta`, enums, and unordered `frozenset` values. RFC 8785 canonicalizes
  JSON values but does not define conversion from these Python values. The
  explicit timestamp and set wire rules in Section 5.4.3 apply only to graph
  observation records.
- Violated invariant: semantically identical digest- or signature-bearing
  values must produce byte-identical canonical bytes across processes,
  adapters, restarts, and supported codec revisions.
- Failure scenario: two conforming implementations encode an equivalent time,
  duration, byte string, enum, optional value, or set differently. Delivery,
  artifact, or signature digests diverge and produce false replay conflicts,
  failed recovery, certificate rejection, or mixed-version incompatibility.
- Prevalence: this affects important retry, durable replay, independent-decoder,
  signed-artifact, and upgrade paths, but need not break one in-process happy
  path.
- Root cause: the design specifies canonical JSON after type conversion without
  specifying one global, versioned conversion from owned typed values to JSON.
- Smallest complete correction: define one owned canonical typed-value profile
  for every digest/signature-bearing ingestion contract. It must cover strict
  UTC datetime encoding, integer duration units and range, canonical binary
  encoding, enum representation, set ordering, Unicode, omission versus null,
  prohibited numeric forms, profile version binding, decoding, rejection, and
  upcast behavior. Existing observation encoding must reference the same profile
  rather than remain an independent rule set.
- Independent verification: two independent encoders must produce identical
  golden bytes and digests. Mutations of timezone form, fraction precision,
  duration unit/sign/range, binary alphabet or padding, set order, Unicode,
  enum value, omission/null, numeric form, or profile version must reject or
  produce the uniquely specified result. Restart and codec-upgrade replay and
  signature verification must preserve the original bytes.

### SIC-007: Traceability excludes authoritative sections and does not prove executed evidence

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: design governance and verification completeness
- Requirement: SIA-R03; affects completion claims for SIA-R01 through SIA-R23
- Evidence: the canonical requirements ledger is authoritative in Section 1
  and the normative solution flow is in Section 2, but Section 3.23.4 extracts
  only Sections 3-5. Each entry has one `primary_sia_requirement_id`, and the
  checker accepts a nonempty registered evidence coordinate without requiring
  content-bound evidence that executed successfully for the frozen revision.
- Violated invariant: every authoritative requirement and material normative
  unit must map to all applicable requirements, measurable assertions, and
  independently verified passing evidence for the exact design revision.
- Failure scenario: a ledger row, scope rule, or workflow step changes without
  a corresponding assertion; a shared unit loses a secondary requirement
  mapping; or a stale, failed, or unexecuted artifact remains registered. The
  two structural parsers can still agree and architecture acceptance can appear
  green.
- Root cause: extraction begins below the source-of-truth sections, coverage is
  one-unit-to-one-primary-requirement, and evidence registration proves naming
  rather than execution and revision binding.
- Smallest complete correction: extract all normative Sections 1-5 with the
  existing closed grammar; self-map every SIA ledger row; make unit-to-SIA
  coverage many-to-many; require explicit defaults or justified overrides for
  every heading; and define independently verifiable evidence records bound to
  unit content key, assertion, test artifact digest, exact implementation and
  design revisions, execution status, result, and trusted issuance context.
- Independent verification: mutate a ledger cell, scope item, workflow item,
  secondary requirement mapping, assertion, revision, execution status,
  artifact digest, or result. Each mutation must fail. Two matching structural
  parsers without valid executed evidence must not satisfy acceptance.

## External Blockers

The following are unchanged, excluded from internal revision, and retain
`Not applicable` product priority with `blocks_approval` disposition:

* `SIA-ED-TOPOLOGY-001`: signed topology, ownership, resource-profile, and
  ordinary-composition authorization.
* `SIA-ED-REPLAY-001`: one governing genesis/checkpoint-consistent
  equal-version replay algebra and matching event-model update.
* `SIA-ED-POLICY-001`: signed initial statistical and monitoring policy with
  independently recomputed evidence.

## Rejected Or Reclassified Findings

* Revision 01's stable identity, governance carrier, message admission, and
  canonical execution graph corrections are internally complete on this
  baseline.
* Missing production implementation remains a later conformance gate, not a
  design defect.
* The traceability issue is not assigned P1/P2/P3 because it is a governance
  and approval defect without a demonstrated product-prevalence claim. Its
  `changes_required` disposition is independent of product priority.
* No retrieval/query, agent-integration, provider-migration, or unrelated
  implementation finding is admitted.

## Round Outcome

**Changes required.** Revision 02 is frozen to SIC-006 and SIC-007. The same
sole design writer may make the smallest complete corrections. After the
revision, the coordinator must freeze a new exact baseline and launch three
fresh whole-design reviewers. The registered external decisions must remain
explicit and unresolved.
