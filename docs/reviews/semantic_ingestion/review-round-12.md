# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-12`
- Review mode: `full`
- Review outcome: `Not approved; bounded non-convergence`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `da450ce335ce8caad62c9496a5a4dd690803907186437f81a05c080012daeeaf`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: dedicated `spec_auditor` (`Aquinas`), dedicated
  `correctness_reviewer` (`Noether`), dedicated `test_reviewer` (`Turing`),
  coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign, agent
  integration, production implementation, and unrelated cleanup remain excluded

All three reviewers independently reviewed the complete frozen design and did
not consult prior review reports. The coordinator validated every proposed
finding against the design, governing requirements, and repository evidence.

## Executive Assessment

Revision 09 closes DREV-059 through DREV-063: operation/fence alignment is now
total and uniquely decidable; source-outcome integrity is separate from hidden
fixture equality; replay-authoritative artifacts publish atomically with their
first references; and retry progress has complete pre-planning and planned
variants.

The design is nevertheless not approved. One P1 and two P2 findings remain.
They are newly exposed violations of existing SIA requirements, not scope
expansion. The third and final revision in the authorized cycle has already
been used, so this report records bounded non-convergence and no further design
edit was made.

## Confirmed Findings

### DREV-064: Writer admission does not fence every semantic write boundary

- Severity: P1 / Blocking
- Requirements: SIA-R11, SIA-R20, and SIA-R21
- Evidence: Section 3.13 promises that embedded, sidecar, and event-consumer
  writers cannot bypass `SemanticWriterCommitBinding`, but it explicitly binds
  only transaction-group CAS. `CommittedGroupAtomicWriteRequest` and
  `NonCommittingGroupAtomicWriteRequest` carry writer admission and epoch;
  `SourceCheckpointAtomicWriteRequest` and
  `SourceFinalizationAtomicWriteRequest` do not. The current generic memory
  store also accepts semantic record writes without a writer-admission
  precondition, so an old process is not fenced merely by adding the new target
  protocol.
- Reproduction: pause an old process after lease acquisition, advance the
  writer epoch in another process, then resume the old generic write. Its graph
  and record preconditions can still pass. A target checkpoint or finalization
  under the old epoch likewise has no modeled admission CAS.
- Root cause: writer admission was attached to graph commit requests instead of
  the common semantic persistence boundary and admitted operation identity.
- Impact: stale or legacy processes can publish progress, results, lifecycle,
  or semantic records after cutover, violating single-writer safety and making
  mixed-version rollout unsafe.
- Required architectural correction: require one
  `SemanticWriterCommitBinding` plus expected writer epoch on admission,
  checkpoint, terminal-group, and finalization writes; bind the admitted
  operation to that epoch; enforce the current binding in the shared storage
  layer for every semantic graph/event/observation/operation/result record kind;
  and drain or terminalize old-epoch operations before cutover. A generic write
  without a current binding must fail closed.
- Independent verification: two real processes over the filesystem backend
  prove stale legacy generic writes, target checkpoints, target group writes,
  and target finalizations all fail after epoch advancement while a current
  writer succeeds and no partial generation is visible.

### DREV-065: The temporal requirement contradicts the predicate temporal-mode contract

- Severity: P2 / Medium
- Requirements: SIA-R03, SIA-R06, SIA-R12, and SIA-R18
- Evidence: SIA-R06 states that omitted temporal expressions cannot promote
  current or historical truth. The detailed contract defines
  `required|optional|atemporal` predicate modes and allows authenticated source
  intervals or trusted event time when no certified textual interval exists;
  only `required` rejects missing evidence.
- Reproduction: provide no textual time for an `optional` predicate but include
  authenticated event time. SIA-R06 requires rejection while the component
  contract permits interval construction and promotion.
- Root cause: “proposer omitted a source-present expression,” “source has no
  textual expression,” “authenticated non-text evidence exists,” and
  “predicate is atemporal” were collapsed into one omission rule.
- Impact: conforming implementations can produce different graphs for the same
  source, and the required omission tests have no unique expected result.
- Required architectural correction: define one normative matrix crossing
  predicate temporal mode (`required`, `optional`, `atemporal`) with evidence
  source (certified text, authenticated source interval, authenticated event
  time, none, ambiguous/misattached text). Revise SIA-R06 and component prose to
  name the same result for every cell, including atemporal facts remaining
  outside temporal supersession.
- Independent verification: table-driven tests cover every matrix cell,
  proposer omission of source-present time, conflicting metadata/text,
  ambiguous attachment, replay, and atemporal projection invariants.

### DREV-066: The preserved legacy lifecycle envelope is not pinned as a complete immutable contract

- Severity: P2 / Medium
- Requirements: SIA-R03 and SIA-R22
- Evidence: SIA-R22 cites a generic “current provider operation contract,” and
  the design lists the four status values, but does not identify the complete
  authoritative response model and serializer at an immutable revision. The
  assessment baseline explicitly includes uncommitted changes while requiring
  byte-compatible legacy-reader behavior.
- Reproduction: add an optional field, change a default or alias, or alter
  serialization while preserving the four status values. The design gives no
  pinned schema or byte fixture against which SIA-R22 can reject the change.
- Root cause: semantic status mapping was specified, but the compatibility
  baseline was left as ambient repository state.
- Impact: implementation and tests must invent which legacy fields, defaults,
  encodings, and failure variants are frozen; main ingestion can work while
  important existing callers break.
- Required architectural correction: pin the authoritative legacy model,
  serializer, and exhaustive payload fixtures by path/symbol and immutable
  revision/tree digest, or define the full legacy wire schema in this design.
  State that the allowed field/schema change set is empty and bind SIA-R22
  verification to that baseline.
- Independent verification: serialize every lifecycle and failure variant and
  compare exact bytes with fixtures extracted from the pinned baseline; an
  API/schema diff gate rejects any added, removed, renamed, retyped, re-aliased,
  or default-changed field.

## Rejected Reviewer Proposals

The test reviewer reported five blockers because the proposed target
architecture and its future acceptance suite are not yet implemented. Those
reports were rejected as review-scope errors: this operation reviews and
revises a proposed design, and both linked WorkPlans explicitly exclude
production code and test implementation. The design already assigns measurable
verification for local-only composition, source admission and egress, semantic
evidence lanes, atomic conformance, replay/migration, and the independent
acceptance oracle. Absence of that future implementation is an implementation
readiness status, not a defect in the design contract.

No test-reviewer proposal was used to weaken a requirement or expand this work
into production implementation.

## Requirements And Verification Status

| Requirement area | Status | Evidence |
| --- | --- | --- |
| DREV-059/DREV-060 operation/fence/source/entity alignment | Closed | Unique partition and operation perfect matching, alternate-matching rejection, permutation and ambiguity tests |
| DREV-061 source-outcome integrity versus fixture equality | Closed | Independent public-record consistency assessment plus disjoint fixture mutation tests |
| DREV-062 replay-artifact publication | Closed | One artifact/state generation, schema registry, closure CAS, failpoint verification |
| DREV-063 pre-planning recovery | Closed | Discriminated progress variants, complete DAG frontier, one-way transition and takeover tests |
| SIA-R11/R20/R21 writer fencing | Open, DREV-064 | Checkpoint/finalization/common-store writer binding is incomplete |
| SIA-R06 temporal evidence | Open, DREV-065 | Required/optional/atemporal decision matrix is contradictory |
| SIA-R22 lifecycle compatibility | Open, DREV-066 | Complete immutable wire baseline is not pinned |
| Other material SIA requirements | No new validated design finding | Full spec/correctness review and coordinator reconciliation |

## Review Limitations

- Reviewers were read-only and made no provider or network calls.
- The test reviewer could not run repository tests in its environment; this did
  not affect the design-level disposition because its reported findings were
  based on missing future implementation rather than contradictory verification
  contracts.
- This report does not claim production readiness or implementation completion.

## Approval Decision

**Not approved; bounded non-convergence.** One P1 and two P2 findings remain.
The exact external decision required is authorization for a new bounded design
revision cycle covering only DREV-064 through DREV-066 and their direct
consistency consequences. Without that authorization, the design must remain
proposed and must not be treated as implementation-ready.
