# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-11`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `a30ff65fb3947ef3c8f73dc6d07db214cb77eed9238b4794e596a652c0e9bd07`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Dirac`), correctness lane
  (`Hilbert`), dedicated `test_reviewer` (`Boole`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign, agent
  integration, production implementation, and unrelated cleanup remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` role launches failed
before repository access because their fixed `gpt-5.6` model was unavailable
for this account. Fresh `gpt-5.4` high-reasoning agents executed those exact
read-only mandates. The dedicated `test_reviewer` ran normally. All three
reviewed the complete frozen design without consulting prior reviewer outputs.

## Executive Assessment

The design is not approved. Five high findings are validated. Two make the
acceptance alignment order under-specified or impossible for ordinary inputs;
one conflates fixture-authored semantics with production-only integrity
coordinates; and two leave replay-authoritative artifacts and pre-planning
retry state outside the closed atomic persistence protocol.

The verification lane otherwise found the design's test strategy complete.
All findings are direct semantic-ingestion architecture defects. None requires
query/retrieval redesign, agent integration, compatibility APIs, or production
implementation in this operation.

## Confirmed Findings

### DREV-059: Source-introduction alignment depends on an operation mapping established later

- Severity: High / P1
- Requirements: SIA-R04, SIA-R17, and SIA-R21
- Evidence: the source-introduction oracle key includes a fixture operation key,
  but the observed record contains an opaque production operation ID. The
  alignment procedure at the frozen baseline says source introductions are
  matched first and operation introductions are matched afterward.
- Root cause: entity bootstrap and operation bootstrap were specified as two
  sequential joins even though source introductions have a foreign key into the
  operation mapping.
- Impact: an implementation must either ignore the operation coordinate, use a
  production ID in the fixture, or infer semantics from later graph records.
- Required correction: align operation introductions before source
  introductions using only fixture-authored source/span/kind/predicate
  coordinates and a globally unique logical-fence equivalence solution. Then
  align source introductions through the established operation mapping and use
  them to establish the entity bijection.
- Completion evidence: zero-, one-, and multiple-solution fixtures prove that
  only one total operation/fence mapping permits source and entity alignment.

### DREV-060: Operation alignment does not define the fence discriminator algorithm

- Severity: High / P1
- Requirements: SIA-R04, SIA-R13, and SIA-R17
- Evidence: `OracleOperationDefinition.operation_fence_key` is required and
  witness verification later requires exact same/different fence classes, but
  the operation-introduction matching prose does not define how fence
  equivalence participates when multiple operations share other coordinates.
- Root cause: fence validation was described after local operation matching
  rather than as a global constraint of the operation bijection.
- Impact: duplicate structural candidates can be paired differently by valid
  implementations, producing nondeterministic witness selection.
- Required correction: define operation alignment as the unique total
  bijection satisfying both local structural coordinates and global fence
  equivalence: equal logical fence keys map to one equal production fence ID,
  and unequal logical keys map to unequal production IDs. Zero or multiple
  solutions fail before source/entity alignment or witness loading.
- Completion evidence: permutation, duplicate-coordinate, same-fence,
  different-fence, replay, and ambiguous-bijection tests agree independently.

### DREV-061: Source-outcome comparison mixes fixture semantics with runtime-only integrity data

- Severity: High / P1
- Requirements: SIA-R03, SIA-R10, SIA-R17, and SIA-R21
- Evidence: `ObservedSourceTerminalOutcome` exposes production fence, group
  result digests, and source result digest, while
  `ExpectedSourceTerminalOutcome` contains no independently authorable
  equivalents. The prose nevertheless states that direct comparison reproduces
  all these fields.
- Root cause: production consistency validation and fixture semantic equality
  were treated as one comparison relation.
- Impact: implementations must copy post-ingest values into the oracle, skip
  integrity fields, or invent expected digests, each invalidating independence.
- Required correction: add an acceptance-side, independently implemented
  production-consistency assessment that validates runtime-only fields against
  the published source result, observation ledger, operation outcomes, and
  group results. Direct fixture equality then compares only pre-ingest
  authorable source identity, operation set, and semantic terminal status.
- Completion evidence: mutating each runtime-only coordinate fails consistency
  validation; mutating each fixture semantic coordinate fails direct equality;
  neither path imports production validators or copies values into fixtures.

### DREV-062: Replay-authoritative artifacts can become visible separately from referencing state

- Severity: High / P1
- Requirements: SIA-R10, SIA-R18, SIA-R20, and SIA-R21
- Evidence: planning, plan, trace, certificate, and authorization artifacts use
  separately described append-only repositories. The atomic store's progress,
  group, and finalization requests can publish references or digests without a
  contract that atomically publishes and indexes the referenced bytes.
- Root cause: content-addressability was mistaken for publication atomicity.
- Impact: a crash can expose progress or terminal state whose replay authority
  is missing even though recovery promises not to repeat paid or learned work.
- Required correction: make all replay-authoritative artifacts part of the
  same generation/transaction as the first visible state that references them.
  Define a typed artifact bundle, one checkpoint write boundary, reference
  closure validation, idempotent collision behavior, and terminal-write
  preconditions that every referenced artifact is already visible in the same
  or an earlier valid generation.
- Completion evidence: exhaustive failpoints around bytes, indexes, and state
  publication expose either the old complete generation or the new complete
  generation; no state can reference a missing or conflicting artifact.

### DREV-063: Retryable progress has no pre-planning state

- Severity: High / P1
- Requirements: SIA-R02, SIA-R10, SIA-R18, and SIA-R20
- Evidence: `SourceIngestionProgress` requires plan lineage and transaction
  groups, but retryable provider, language-analysis, normalization, and storage
  failures can occur before any plan exists.
- Root cause: retry progress was modeled only after graph planning.
- Impact: implementations must invent sentinel plans, discard reusable learned
  artifacts, or terminalize a retryable pre-planning failure.
- Required correction: define discriminated pre-planning and planned progress
  variants, a one-way atomic transition between them, exact next-stage and
  artifact-bundle coordinates, and bounded resume behavior without sentinel
  plan or group identities.
- Completion evidence: failure injection at every source stage, ownership
  takeover, lost acknowledgement, and pre-planning-to-planned transition proves
  exact bounded resume without repeated acknowledged learned calls.

## Rejected And Consolidated Reviewer Proposals

- The test lane reported no blocking, high, or medium verification finding.
- The two alignment reports remain separate because one is an impossible local
  ordering and the other is a missing global uniqueness constraint; both must
  hold for the algorithm to be total.
- Runtime-only source digests will not be added to the hidden fixture. They are
  production integrity coordinates and require an independent consistency
  check, not fixture authorship.
- Artifact publication will not be repaired with best-effort repository writes
  or recovery-time reconstruction. First visibility of a reference and its
  canonical bytes must share one atomic generation.

## Approval Decision

**Changes required.** DREV-059 through DREV-063 must be resolved in the final
permitted revision, and the entire revised design must pass a fresh independent
review. If that review validates any blocking, high, or medium finding, the
workflow must stop as non-converged because no revision budget remains.
