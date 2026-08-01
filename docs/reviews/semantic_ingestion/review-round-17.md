# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-17`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `a632772d2b7485a9b105d7e7c02dbf76881d8f1e8da4f33430f6931c86f2b029`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: fresh `spec_auditor` (`Euclid`), fresh
  `correctness_reviewer` (`Popper`), fresh `test_reviewer` (`Nietzsche`),
  coordinator validation
- Scope: complete semantic-ingestion design; retrieval remains excluded
- Prior-report rule: reviewers completed independent passes before the
  coordinator consulted unresolved round-16 findings

## Executive Assessment

The design is not approved. The fresh reviewers found one replay-contract
defect and three verification defects. After their independent passes, the
coordinator revalidated every unresolved round-16 finding against the unchanged
baseline; all still reproduce. The resulting frozen inventory is DREV-077,
DREV-079 through DREV-087. No other work enters revision 13.

## Continuing Validated Findings

### DREV-077: Governing same-version replay semantics conflict

- Requirements: SIA-R03, SIA-R10.
- Failure: `docs/design/event_model.md` Section 8.2 uses `event_id` precedence,
  while Sections 9.2 and 10.2 skip an equal version.
- Required external decision: the event-model owner must choose canonical
  behavior for exact duplicates, conflicting historical equal-version events,
  and current-writer equal-version submissions.

### DREV-079: Graph-free normalization binds graph-dependent groups

- Requirements: SIA-R02, SIA-R04, SIA-R19, SIA-R20.
- Failure: source normalization forbids graph state but source grouping requires
  snapshot-bound canonical identity resolution.
- Required correction: introduce graph-free `SourceDependencyGroup` and reserve
  identity-sensitive expansion for `TransactionSemanticGroupPlan`.

### DREV-080: Reservation authority contradicts lease recovery

- Requirements: SIA-R04, SIA-R20, SIA-R21.
- Failure: reservation prose requires current lease identity while reclaim
  requires immutable reservation bytes under a rotating lease.
- Required correction: keep reservations immutable and add renewable
  `ReservationUseAuthorization` checked at validation and CAS.

### DREV-081: Temporal provenance is incomplete for transition operations

- Requirements: SIA-R06, SIA-R12, SIA-R17, SIA-R18.
- Failure: corrections, retractions, and identity transitions cannot preserve
  and expose complete accepted temporal evidence through replay and oracle
  comparison.
- Required correction: carry one complete temporal evidence object through
  accepted, durable, expected, and observed transition contracts.

### DREV-082: Oracle-only temporal mutations require an impossible outcome

- Requirements: SIA-R12, SIA-R17.
- Failure: post-commit fixture or observation mutations cannot legitimately
  produce zero graph visibility.
- Required correction: production-boundary mutations prevent visibility;
  oracle/comparator mutations fail acceptance while leaving graph bytes
  unchanged.

### DREV-083: Production test-hook absence lacks independent evidence

- Requirements: SIA-R21.
- Failure: test hooks are prohibited, but no closed production surface or
  package/schema audit proves their absence.
- Required correction: add a production contract-surface manifest and external
  fault-supervisor verification.

## Newly Validated Findings

### DREV-084: Checkpoint watermark cannot identify the replay suffix

- Severity: high.
- Requirements: SIA-R10.
- Evidence: `SemanticReplayCheckpoint` contains no durable ordered log position,
  but replay resumes strictly after its watermark. Content-derived event IDs
  and within-batch ordering cannot order later batches.
- Failure invariant: a later batch with a lexically smaller event ID may be
  omitted or replayed according to backend-specific order.
- Required correction: assign an opaque repository-scoped monotonic batch
  position atomically with each batch; bind it into checkpoint integrity and
  define continuity-validating `read_batches_after(position)`.
- Independent verification: checkpoint A, append B with smaller event IDs,
  restart both backends, and require B exactly once; reject missing, duplicate,
  reordered, or substituted positions.

### DREV-085: Statistical certification completeness is self-referential

- Severity: high.
- Requirements: SIA-R14.
- Evidence: statistical gates use free-form metric IDs, while the referenced
  certified capability matrix is not a closed activation-bound authority.
- Failure invariant: a behavior lane omitted from the gate manifest cannot be
  detected by recomputing that same manifest.
- Required correction: add a signed closed capability-coverage manifest over
  enabled and explicitly unsupported language, predicate, construction, and
  behavior-lane cells. Activation requires an exact gate bijection.
- Independent verification: enable each behavior lane while omitting, adding,
  or substituting its coverage row or gate; activation must fail independently
  of runtime selection code.

### DREV-086: Zero-egress proof bypasses the real remote composition path

- Severity: high.
- Requirements: SIA-R09.
- Evidence: negative tests prove only that a fake transport adapter is not
  invoked. They do not exercise the production factory and real remote adapter
  to the wire boundary.
- Failure invariant: a factory or alternate-client regression can emit source
  bytes while the fake adapter remains untouched.
- Required correction: require an ordinary production-root integration test
  with the real remote adapter pointed at a controlled capture endpoint.
- Independent verification: denied decisions produce zero connections,
  requests, fallback, or graph effects; an allowed control reaches exactly the
  configured endpoint once.

### DREV-087: Fixture-review independence is identity-only

- Severity: medium.
- Requirements: SIA-R17.
- Evidence: two distinct qualified reviewer IDs satisfy the contract without
  fixture-author separation, independence domains, or blinded commitments.
- Failure invariant: one authoring group can approve the same hidden-oracle
  misconception under two identities.
- Required correction: bind fixture-author provenance, reviewer independence
  domains, blinded initial commitments, and an independent adjudicator into the
  acceptance-only review authority.
- Independent verification: same-domain reviewers, author-reviewers, and
  adjudicators from either primary domain fail before ingest; qualified
  independent commitments with complete coverage pass.

## Reviewer And Coordinator Dispositions

- The spec lane proposed no finding. Its result does not invalidate directly
  reproduced contradictions that remained from the prior immutable baseline.
- The correctness lane's replay cursor finding is confirmed as DREV-084.
- The test lane's certification, egress, and fixture-review findings are
  confirmed as DREV-085 through DREV-087.
- DREV-077 and DREV-079 through DREV-083 were revalidated only after all fresh
  reviewers completed their independent passes.
- No implementation-absence, retrieval, agent-integration, or unrelated
  cleanup finding was accepted.

## Approval Decision

**Changes required.** Revision 13 is authorized for DREV-079 through DREV-087
and direct consistency consequences. DREV-077 remains an external blocker and
cannot be silently resolved by this lower-precedence design.
