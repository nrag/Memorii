# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-16`
- Review mode: `full`
- Review outcome: `Blocked`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `a632772d2b7485a9b105d7e7c02dbf76881d8f1e8da4f33430f6931c86f2b029`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: fresh `spec_auditor` (`Kepler`), fresh
  `correctness_reviewer` (`Lovelace`), fresh `test_reviewer` (`Jason`),
  coordinator validation
- Scope: complete semantic-ingestion design; no reviewer read a prior report
- Revision budget: three of three revisions used in this authorized cycle

## Executive Assessment

The design is not approved. Revision 12 closes DREV-078 for facts and action
records, but the full review found that the same provenance invariant is not
representable for retractions and identity transitions. It also validated two
blocking contract contradictions introduced or left exposed by revisions 10
and 11, one impossible test assertion, and one missing independent prohibition
against production test hooks. DREV-077 remains an external governing-source
blocker.

The authorized three-revision budget is exhausted. No fourth revision was made.
This report records the exact architectural corrections and external decision
required for a new bounded cycle.

## Validated Blocking Findings

### DREV-077: The governing event model has contradictory same-version replay rules

- Requirements: SIA-R03, SIA-R10.
- Failure: `docs/design/event_model.md` Section 8.2 uses `event_id`
  precedence, while Sections 9.2 and 10.2 skip an equal version. Conflicting
  same-record/same-version history is arrival-order dependent under one rule
  and deterministic under the other.
- Required external decision: the event-model owner must define canonical
  behavior for byte-identical duplicates, conflicting historical equal-version
  events, and current-writer equal-version submissions, then reconcile Sections
  8.2, 9.2, 10.2, and the target design.
- Independent evidence: apply two conflicting valid same-version events in both
  orders from genesis and checkpoint replay; verify one identical terminal
  state. Separately verify exact duplicates and current-writer collision
  behavior.

### DREV-079: Graph-free normalization binds graph-dependent source groups

- Requirements: SIA-R02, SIA-R04, SIA-R19, SIA-R20.
- Failure: `SourceNormalizationRequest` forbids graph state and produces
  `SourceSemanticGroup`, which capability selection and NLI bind before graph
  work. The grouping prose nevertheless requires snapshot-bound canonical
  identity resolution. Changing only graph identity can therefore change a
  supposedly immutable graph-free group.
- Required architectural correction: define a graph-free
  `SourceDependencyGroup` from source spans and explicit source dependencies
  only. Bind capability selection and NLI to it. Perform identity-sensitive
  expansion later in `TransactionSemanticGroupPlan`.
- Independent evidence: vary graph identity resolution while holding all source
  artifacts fixed. Source group IDs, capability selections, and NLI artifacts
  must remain byte-identical; only transaction planning may change.

### DREV-080: Reservation authority contradicts lease recovery

- Requirements: SIA-R04, SIA-R20, SIA-R21.
- Failure: prose requires reservations to persist the current lease-binding
  digest, but `PlannedIdentityReservation` and `PlannedActionReservation` have
  no such field. Reclaim simultaneously requires reservation bytes and digests
  to remain unchanged while the lease binding rotates.
- Required architectural correction: keep reservations immutable allocation
  artifacts. Add renewable `ReservationUseAuthorization` binding reservation
  digest, operation/fence, and current lease binding; require it at validation
  and CAS and rotate it on reclaim.
- Independent evidence: in two processes, reclaim with the same reservation
  digest and a new authorization. The old authorization and every swapped
  reservation/authorization pair must fail before mutation.

## Validated High Findings

### DREV-081: Temporal provenance is incomplete for retractions and identity transitions

- Requirements: SIA-R06, SIA-R12, SIA-R17, SIA-R18.
- Failure: `AcceptedRetraction` and `AcceptedIdentityOperation` carry only
  `EffectiveTimeCoordinate`; durable, expected, and observed identity
  transitions likewise omit complete `AcceptedTemporalEvidence`. Equal numeric
  time with different authenticated reference or source-interval provenance is
  therefore indistinguishable.
- Required architectural correction: attach one shared complete temporal
  evidence object to correction transitions, retractions, and identity
  operations; persist and expose it through durable records, replay, expected
  fixtures, observed records, and mandatory boundary profiles.
- Independent evidence: for every operation type, hold numeric values constant
  while independently swapping reference kind, source field, authority basis,
  provenance digest, reference digest, and source-interval evidence digest.

### DREV-082: The oracle-only temporal mutation assertion requires an impossible outcome

- Requirements: SIA-R12, SIA-R17.
- Failure: the validation strategy requires expected-fixture and observed-page
  substitutions to produce zero graph visibility. Those mutations happen after
  a valid production commit and cannot legitimately hide or roll back the
  graph.
- Required correction: split outcomes by boundary. Production-input,
  accepted-IR, durable, and replay mutations must prevent visibility.
  Expected-fixture, serialized-observation, and comparator mutations must fail
  acceptance, emit no pass artifact, and leave the authorized graph unchanged.
- Independent evidence: commit once, mutate only expected or serialized
  observed evidence, and require deterministic comparison failure with
  byte-identical production graph state.

## Validated Medium Finding

### DREV-083: Absence of production test hooks is not independently verifiable

- Requirements: SIA-R21.
- Failure: the design prohibits scheduler, failpoint, and test concepts in
  production contracts and suggests external process coordination, but defines
  no closed production surface or evidence proving those controls are absent.
- Required correction: define a production contract-surface manifest and
  require static export/schema/package checks that reject test-only modules,
  hook parameters, failpoint states, and test configuration fields. Define the
  fault harness as an external process/filesystem supervisor.
- Independent evidence: execute crash schedules against an unmodified
  production artifact through the external supervisor, then audit the manifest,
  package exports, and public schemas for forbidden harness controls.

## Coordinator Validation

- DREV-077 is confirmed by the contradictory higher-precedence event-model
  text and requires an external owner decision.
- DREV-079 and DREV-080 are confirmed by direct contradictions between typed
  contracts and normative prose.
- DREV-081 is confirmed as incomplete propagation of DREV-078 rather than a
  new scope area.
- DREV-082 is confirmed because acceptance-only mutations cannot retroactively
  produce zero production visibility.
- DREV-083 is confirmed as a missing design-level verification invariant, not
  an implementation-absence complaint.
- Retrieval, agent integration, current implementation completeness, and
  unrelated cleanup remain outside scope.

## Approval Decision

**Blocked after bounded non-convergence.** Approval requires a newly authorized
revision cycle limited to DREV-079 through DREV-083 and direct consistency
consequences, plus the event-model owner decision for DREV-077. The design must
then receive a fresh full review at an exact frozen SHA-256 baseline.
