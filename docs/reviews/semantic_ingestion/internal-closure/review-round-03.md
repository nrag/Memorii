# Design Review: Semantic Ingestion Internal Closure, Round 03

## Review Metadata

- Review ID: `semantic-ingestion-internal-closure-round-03`
- Review mode: `full`
- Review outcome: `Changes required; final permitted revision authorized`
- Design baseline SHA-256:
  `4c4d2a4708358838d77b5d8da375f65d5f86da9283bcbb9ff1e47ff39fb90709`
- Design size: 14,018 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation

## Executive Assessment

The spec auditor approved the complete design. The test reviewer reported only
absence of the proposed implementation and executable implementation evidence;
those observations are valid future conformance work but are not defects in a
target architecture document and are rejected from this design revision.

The correctness reviewer found three concrete internal contract defects. Direct
inspection confirms all three. The frozen round-03 inventory is three P2
findings, no P1 finding, and no additional governance finding. This authorizes
the third and final permitted design revision. The three registered external
decisions remain separate and unchanged.

## Confirmed Internal Findings

### SIC-008: Structured-source spans conflate retained, projection, and segment coordinates

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: provenance and typed coordinate correctness
- Requirements: SIA-R01, SIA-R04, SIA-R10, SIA-R12, and SIA-R17
- Evidence: `TextSpan` is defined over the exact retained source string, but
  `SemanticProjectionSegment`, `SourceSpanReference`, preparation, and
  downstream evidence reuse it for projection and segment-local offsets.
  Structured snapshots retain canonical envelope JSON while semantic projection
  contains decoded message content, so equal offsets do not address equal text.
- Violated invariant: every evidence span must name exactly one immutable text
  artifact and coordinate space, and every structured projection must retain a
  reversible, independently verifiable mapping to its envelope field.
- Failure scenario: a snapshot retains `{"content":"Alice owns Atlas"}` while
  its projected segment is `Alice owns Atlas`. Projection offsets and hashes
  cannot satisfy a span contract defined over the retained JSON string.
- Prevalence: structured snapshots and delegation results are important
  integration/recovery paths, while an ordinary verbatim turn remains valid.
- Root cause: one span schema and `source_digest` field were reused for three
  non-isomorphic text coordinate spaces.
- Smallest complete correction: define a closed text-artifact coordinate
  contract for retained text, projection text, and segment text; make every span
  bind one artifact kind, ID/digest, length, and exact substring digest. For
  structured input, add an envelope-field reference that binds canonical JSON
  pointer, exact canonical field-value bytes/digest, decoded content digest,
  projection segment, and segment text. Downstream evidence must use explicit
  projection/segment coordinates and retain the envelope mapping without
  pretending JSON offsets equal decoded-content offsets.
- Independent verification: multi-message snapshots and delegation envelopes
  must round-trip when JSON and decoded-content offsets differ. Mutating any
  artifact kind, ID, digest, length, pointer, canonical field bytes, decoded
  value, separator, projection coordinate, or segment coordinate must reject.

### SIC-009: Source-wide language routing can certify mixed-language segments

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: capability and semantic-safety boundary
- Requirements: SIA-R02, SIA-R04, SIA-R15, and SIA-R16
- Evidence: `PreparedSource` contains one `LanguageRoutingDecision`; proposal,
  both analyzers, event detection, and temporal resolution consume that same
  selected language even though source execution and governance are
  segment-scoped. `code_switch_spans` has no mandatory non-promotion rule.
- Violated invariant: every promoted segment must execute only under a
  language/capability decision certified for that exact segment.
- Failure scenario: one governed snapshot contains English and Spanish
  messages. Aggregate routing selects English and permits the Spanish segment
  to use English proposer/analyzer/resolver resources.
- Prevalence: multilingual or code-switched governed snapshots are important
  supported English/Spanish cases, not the dominant single-language turn.
- Root cause: segment-scoped semantic execution is paired with a source-scoped
  route and an observational-only code-switch field.
- Smallest complete correction: make routing decisions and capability bindings
  segment-scoped and content-bound. Every learned or linguistic request must
  carry the exact selected route for its segment. Within-segment unresolved code
  switching, uncertain/unsupported/conflicting routing, or missing certified
  resources makes that segment evidence-only with zero learned call and graph
  effect. Source status is a total aggregation of segment outcomes, not an
  authority that changes them.
- Independent verification: mixed English/Spanish messages, within-segment code
  switching, incorrect declared language, router disagreement, missing resource,
  route substitution, batching, retry, and replay must prove no cross-language
  capability execution and no active graph effect without a selected certified
  per-segment route.

### SIC-010: Result lookup does not authorize every scope in a composite outcome

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: access control and non-disclosure
- Requirements: SIA-R01, SIA-R09, SIA-R22, and SIA-R23
- Evidence: governed snapshot messages may carry distinct authenticated
  effective scopes. A successful lookup returns the complete source result,
  carrier sets, and carrier artifact, but authorization requires only the
  singular admitted source scope to belong to the caller's current scope set.
- Violated invariant: authorization must cover every scope represented in a
  returned artifact before any result repository lookup or disclosure.
- Failure scenario: a snapshot contains task-A and task-B messages. A principal
  currently authorized only for task A passes the source-scope check and
  receives task-B carrier and group outcome data.
- Prevalence: mixed-scope lifecycle snapshots are important integration and
  security cases, not the dominant single-turn path.
- Root cause: admission/result artifacts are segment-scoped while result-access
  authorization is source-scoped.
- Smallest complete correction: persist one canonical complete required-scope
  set and digest in the protected admission/carrier generation. Before result
  lookup, the authorizer must load that protected admission index and require
  current authorization to cover every scope exactly represented by the
  outcome. The existing complete-source lookup has no partial filtering or
  per-scope projection fallback; insufficient coverage returns the identical
  non-disclosing unavailable result without repository access.
- Independent verification: mixed-scope snapshots with zero, partial, exact,
  superset, stale, revoked, substituted, or cross-tenant current authorization
  must prove complete coverage is required, denial is indistinguishable and
  mutation-free, and no result/artifact repository read occurs before approval.

## Rejected Findings

* Missing target production implementation is not a defect in a proposed
  target-architecture design. It is an implementation WorkPlan and conformance
  gate.
* Existing legacy unit tests do not certify this target architecture, but the
  design already specifies independent production-boundary verification. Their
  present absence is implementation work, not missing design semantics.
* Missing executed exact-revision evidence at the current implementation SHA is
  expected before implementation. The revised design now defines the evidence
  contract and rejects approval without it.
* No retrieval/query redesign, agent integration, provider migration, or
  unrelated cleanup is admitted.

## External Blockers

`SIA-ED-TOPOLOGY-001`, `SIA-ED-REPLAY-001`, and `SIA-ED-POLICY-001` remain
unchanged with `Not applicable` product priority and `blocks_approval`
disposition.

## Round Outcome

**Changes required.** Revision 03 is frozen to SIC-008 through SIC-010 and is
the final permitted design revision. The same sole writer may make only the
smallest complete corrections. A fresh full review must then either approve the
design internally or produce an unresolved-findings report; no fourth revision
is permitted in this operation.
