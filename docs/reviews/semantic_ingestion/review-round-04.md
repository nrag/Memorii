# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-04`
- Review mode: `full`
- Review outcome: `Changes required; revision budget exhausted`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `82e21dc7fb2670c8649149b58e8dd61c2e614de7480e0e7eccc9ae21bb3ed320`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Euler`), correctness lane
  (`Lorentz`), dedicated `test_reviewer` (`Kant`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and production
  implementation remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` roles failed before
repository access because their fixed `gpt-5.6` model is unavailable for this
account. Fresh `gpt-5.4` high-reasoning agents executed those exact independent
mandates. The dedicated `test_reviewer` ran normally. All three reviewed the
complete frozen design without seeing another lane's findings.

## Executive Assessment

Revision 03 closes DREV-023 through DREV-027. The spec-audit and test lanes
approved the complete design with no blocking, high, or medium findings. The
correctness lane found one P1 and one P2 contract contradiction. The coordinator
validated both directly against the frozen design and governing event and
implementation rules.

The design is not approved. Three revision rounds have already been used, so
the workflow stops without modifying the frozen revision-03 baseline.

## Confirmed Unresolved Findings

### DREV-028: Delete events are not full-state replay records

- Severity: High / P1
- Governing requirement: canonical event model Sections 5.1-5.2; SIA-R10
- Evidence: `DeletedMemoryRecordSnapshot` contains only record identity, prior
  digest, deletion authorization digest, and `deleted=True`, while the design
  calls it a tombstone full-state payload. The governing event model requires
  every event entity to contain the complete state needed to reconstruct the
  object and forbids prior in-memory state or implicit defaults.
- Root cause: the delete variant models evidence that a deletion happened, not
  the complete durable deleted-object state required by the chosen full-
  snapshot event model.
- Impact: genesis, checkpoint, and mixed-schema replay must invent whether to
  load the prior object, synthesize omitted tombstone fields, or consult
  non-event storage.
- Exact architectural change needed: make the delete event carry a complete
  typed deleted-memory-record snapshot, including the canonical prior record
  payload, record kind and ID, prior record digest and version, tombstone record
  version, deletion authorization digest, and `deleted=True`. Its event digest,
  logical-mutation digest, schema upcasters, and checkpoint replay must cover
  that complete snapshot. No replay path may consult prior in-memory or
  non-event state to materialize the tombstone.
- Completion evidence: genesis, signed-checkpoint, mixed-schema, and isolated
  post-checkpoint delete replay reconstruct the exact tombstone; removing or
  mutating any deleted-record field fails before state exposure.

### DREV-029: Source summaries cannot represent per-attempt plan lineage

- Severity: Medium / P2
- Governing requirement: SIA-R04; `docs/IMPLEMENTATION_RULES.md` explicit,
  typed, auditable semantics
- Evidence: each graph-dependent retry rematerializes a group plan and
  authorizes the group under that newly referenced plan.
  `TransactionGroupExecutionResult` carries no plan, attempt, or planning-
  authorization reference, while `GraphBoundSourceIngestionResult` and its
  persistence request expose one global transaction-group plan and require all
  group results to be a bijection with it.
- Root cause: the source terminal contract assumes one immutable plan while the
  retry contract permits a lineage of attempt-specific plans.
- Impact: after one group commits and another replans, an auditor cannot recover
  which exact plan and authorization produced each terminal result without
  inference.
- Exact architectural change needed: introduce a typed source plan-lineage
  artifact that retains the initial source plan and every superseding
  attempt-specific plan reference. Add exact `authorizing_attempt_digest`,
  `authorizing_group_plan`, and `planning_authorization_digest` fields to every
  terminal group result. Aggregate source status over those explicit
  per-result bindings and define invariants that committed groups cannot be
  regrouped, removed, or semantically changed by later plans. Replace the
  ambiguous single-plan bijection with a lineage validation proving every
  terminal group has exactly one eligible authorizing attempt and that the
  terminal result set covers the final unresolved/committed source partition.
- Completion evidence: a deterministic run where group A commits, group B
  encounters a related conflict and replans, and the terminal summary
  independently identifies the exact plan, attempt, authorization, and result
  for both groups; missing, duplicate, stale, regrouped, or cross-plan bindings
  fail validation.

## Approved Lanes And Rejected Concerns

- The independent spec-audit lane found no remaining scope, traceability,
  consistency, compatibility, or failure-recovery blocker.
- The dedicated test-review lane found measurable, independent verification for
  SIA-R01 through SIA-R21, including schema evolution, dedupe/restart,
  checkpoint trust, filesystem crash atomicity, oracle isolation, and
  statistical gates.
- Retrieval redesign, production implementation absence, and broader language
  expansion remain outside this review and were not admitted as findings.

## Stop Condition

The workflow did not converge within three revision rounds.

Resumption requires an explicit decision authorizing one additional bounded
revision containing only DREV-028 and DREV-029, followed by a fresh full review.
The required architectural choices are fixed in the findings above: full typed
delete snapshots and explicit per-group authorizing-plan lineage. No external
product semantics or retrieval decision is required.

## Outcome

`Changes required; blocked by revision budget`. The frozen revision-03 design
must not be treated as approved or implementation-ready until DREV-028 and
DREV-029 are corrected and a fresh whole-design review approves the new
baseline.
