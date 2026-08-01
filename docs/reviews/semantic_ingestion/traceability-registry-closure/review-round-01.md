# Semantic Ingestion Traceability Registry Closure Review, Round 01

## Review Metadata

- Review date: 2026-07-27
- Review mode: full, read-only, independent design review
- Repository revision:
  `237053aef26fae2df7e6b44144e61a1b780bf7ad`
- Design baseline:
  `f94e76033f06e10c0f7b8fd6d0905c7d9f70202f3e7e39d11b2ce65588c3aed0`
- Design size: 15,073 lines
- Reviewers: fresh `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer` instances
- Revision count before this review: 0 of 3

The reviewers received the frozen design and governing requirements without
prior review reports or a coordinator conclusion. The current untracked
traceability implementation and tests were read only as feasibility evidence
and were not modified.

## Priority And Approval Interpretation

The repository taxonomy reserves P1 and P2 for demonstrated product behavior:

- P1: mainstream/default product scenarios are broken and shipping is blocked.
- P2: important remaining product scenarios are broken and shipping is not
  advisable.
- P3: fit and finish only.
- Not applicable: governance, verification, or external-decision defects that
  do not themselves demonstrate broken product behavior.

Approval disposition is independent of product priority. Both findings below
are therefore `Not applicable` for product priority and `blocks_approval` for
design disposition. Reviewer labels of P1 or P2 were normalized by the
coordinator because the evidence concerns design-completeness and release
governance, not a demonstrated runtime use-case failure.

## Validated Findings

### TRC-001: Required traceability registry instances have no authoritative source

- Product priority: Not applicable
- Approval disposition: `blocks_approval`
- Confidence: high
- Finding type: design completeness, governance, verification
- Requirements: SIA-R03 and SIA-R13

#### Evidence

SIA-R03 requires closed structural extraction, complete mappings from every
Sections 1-5 unit to requirements, owners, versioned assertions, and test
groups, plus trusted exact-revision evidence. Section 3.23.4 further requires:

- exactly one `SectionTraceabilityDefault` for every Sections 1-5 heading;
- complete closed `StructuralRequirementMappingRule` contents;
- versioned assertion and test-evidence bindings;
- explicit overrides and anchor bindings;
- one coverage approval for every heading.

The design defines schemas for those records but contains no complete registry
instances and names no authoritative artifact containing them. Repository
search finds only the class declarations in the design. The current
implementation tests construct synthetic mappings, including assigning sample
units to SIA-R03, so they demonstrate parser feasibility but cannot supply the
missing normative data.

#### Violated invariant

An implementation must be able to construct one unique
`NormativeTraceabilityManifest` from published normative inputs without
inventing semantic mappings. The frozen baseline cannot satisfy this
invariant: an implementer must choose heading defaults, structural rules,
assertion bindings, overrides, anchors, and approval contents.

#### Required correction

Publish a design-owned, canonical, content-addressed traceability registry
source package for the exact design revision. It must contain the complete
instances for all required registry roots, including explicit empty sets where
the closed grammar permits them. The design must define deterministic
serialization, path and heading identity, completeness, versioning, mutation,
publication, supersession, and compatibility rules. The design must reference
the artifact through a non-circular binding: the design identifies its stable
location and schema, while the registry release binds the final design digest.

#### Required verification

- Independently enumerate every Sections 1-5 heading and require exactly one
  default entry.
- Require every SIA-R01 through SIA-R23 ledger row to self-map.
- Resolve every structural selector, assertion/version, test group, override,
  and explicit anchor without an inferred fallback.
- Mutate, add, remove, reorder, or substitute each registry root and require
  deterministic rejection or the specified canonical equivalence.
- Prove that current synthetic mappings cannot satisfy acceptance for the real
  design.

#### Completion evidence

A checked-in complete registry source package bound to the revised design,
deterministic independent reconstruction of byte-identical registry roots, and
a fresh whole-design review that requires no invented material mapping.

### TRC-002: Traceability registry release and trust authority are undefined

- Product priority: Not applicable
- Approval disposition: `blocks_approval`
- Confidence: high
- Finding type: governance, trust, release lifecycle
- Requirements: SIA-R03 and SIA-R13

#### Evidence

`TraceabilityCoverageApprovalRecord` and
`NormativeExecutionEvidenceRecord` contain opaque reviewer/issuer and trust
digests, but the design does not identify the authority that creates the
initial registry release, qualifies reviewers and issuers, publishes trusted
keys, activates a release, or handles supersession, revocation, compromise,
expiry, rollback, and recovery. `NormativeTraceabilityManifest` has no release
identity, sequence, lifecycle state, signer, or supersession binding.

The acceptance release taxonomy governs graph-oracle registries but not the
SIA-R03 traceability registry. Section 1.5.2 declares exactly three unresolved
external decisions, and none owns traceability registry approval or release
trust.

#### Violated invariant

The acceptance system must distinguish one active, authorized, exact-design
traceability release from a substituted, stale, rolled-back, revoked, or
caller-invented package. The frozen baseline has no normative input from which
that decision can be made.

#### Required correction

Define the complete internal release contract and add a registered external
decision only for values that the design cannot legitimately invent:
traceability approval authority, qualified reviewer and evidence-issuer
identities, trusted keys, and the initial signed active release. The contract
must bind the complete registry roots, exact design digest, assertion artifact,
coverage approvals, purpose, trust snapshot, monotonic epoch or sequence,
active/superseded/revoked/compromised state, expiry, rollback protection, and
atomic publication/recovery. Historical evidence verifies under its original
valid binding; a design, grammar, assertion, or registry-content change
requires a new release.

Execution evidence must bind a conforming runner report, command/test
selection, immutable result bytes, runner identity, implementation revision,
and implementation tree. A signature over arbitrary success-shaped bytes is
insufficient.

#### Required verification

- Reject unknown, wrong-purpose, unqualified, revoked, compromised, expired,
  superseded, or rollback signer/reviewer states.
- Reject valid older releases after a newer active sequence.
- Reject cross-design, cross-registry, cross-assertion, and cross-purpose
  substitution.
- Reject signed arbitrary result bytes without a conforming execution report.
- Exercise atomic publication interruption and recovery without exposing a
  partial active release.

#### Completion evidence

A complete release/trust contract, one explicit registered external decision
for its externally owned identities and initial activation, and a fresh review
confirming that no implementation choice remains implicit.

## Rejected Or Reclassified Reviewer Observations

- Current extractor unit-kind gaps, checker import coupling, and synthetic test
  mappings are implementation findings against the proposed design, not
  additional design defects. They remain untouched in this design operation.
- The test reviewer's statement that `AGENTS.md` was absent was a reviewer
  environment error; the coordinator read the repository file directly.
- Existing unresolved topology, replay, and statistical-policy decisions are
  unchanged and are not findings introduced by this review.

## Self-Review

- Every validated finding is supported by direct design and repository
  evidence.
- No product P1 or P2 label is used for a governance-only defect.
- The proposed correction does not infer heading semantics, collapse registry
  roots, modify production code, or select external identity/key values.
- The correction can be independently verified without importing generator
  logic.
- Current user implementation files remain unchanged.

## Disposition

**Not approved.** Two validated internal design-completeness findings block
approval. One bounded revision is authorized for TRC-001 and TRC-002. The
revision must preserve all unrelated design behavior and current implementation
work, then receive a fresh full review from new reviewer instances.
