# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-05`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `82e21dc7fb2670c8649149b58e8dd61c2e614de7480e0e7eccc9ae21bb3ed320`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Faraday`), correctness lane
  (`Maxwell`), dedicated `test_reviewer` (`Carson`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and production
  implementation remain excluded

Existing reports are immutable under `$review-design`; this newly authorized
cycle therefore continues at round 05 rather than overwriting the existing
`review-round-01.md`.

The dedicated `spec_auditor` and `correctness_reviewer` roles failed before
repository access because their fixed `gpt-5.6` model is unavailable for this
account. Fresh `gpt-5.4` high-reasoning agents executed those exact independent
mandates. The dedicated `test_reviewer` ran normally. All three reviewed the
complete frozen design without seeing another lane's findings.

## Executive Assessment

The full review independently reconfirmed DREV-028 and DREV-029. It also found
two integration ambiguities that would require invented public or persisted
semantics: the target terminal-result lattice has no migration mapping to the
existing provider-facing operation envelope, and semantic event identity is not
normatively equated with compiler record identity.

Four findings block approval: two P1 and two P2. The revision must remain
limited to these contracts and their direct verification and traceability
consequences.

## Confirmed Findings

### DREV-028: Delete events are not full-state replay records

- Severity: High / P1
- Governing requirement: canonical event model Sections 5.1-5.2; SIA-R10
- Evidence: `DeletedMemoryRecordSnapshot` retains only record identity and
  digests while the design calls it a tombstone full-state payload. The
  governing event model forbids replay from relying on prior in-memory state,
  implicit defaults, or missing fields.
- Root cause: the delete variant proves deletion but cannot independently
  reconstruct the complete deleted record.
- Required correction: carry a complete typed deleted-record snapshot,
  including the prior canonical record and record version, tombstone version,
  deletion authorization, and all replay identity/digest fields.
- Independent verification: genesis, checkpoint, mixed-schema, and isolated
  post-checkpoint delete replay plus one-field omission/mutation tests.

### DREV-029: Terminal summaries lose attempt-specific plan lineage

- Severity: Medium / P2
- Governing requirement: SIA-R04; implementation rules for explicit typed and
  auditable semantics
- Evidence: graph-dependent retries create attempt-specific plans and
  authorizations, but terminal group results name neither, while the source
  result exposes one global plan.
- Root cause: the terminal contract assumes a single plan although the retry
  contract permits a plan lineage.
- Required correction: define a typed source plan-lineage artifact and bind
  every terminal group result to its exact attempt, group plan, and planning
  authorization. Define immutable committed-group and final-partition
  invariants.
- Independent verification: group A commits, group B replans after conflict;
  exact lineage remains reconstructable and stale, duplicate, regrouped, or
  cross-plan bindings fail.

### DREV-030: Target semantic outcomes have no public compatibility mapping

- Severity: High / P1
- Governing requirement: `$review-design` mixed-version and migration review;
  SIA-R04 and SIA-R19
- Evidence: the target defines `fully_committed`, `partially_committed`,
  `evidence_only`, `rejected`, and `unresolved`, while existing provider and
  durable operation contracts expose only pending, running, committed, and
  failed lifecycle statuses. The design specifies no mapping or additive result
  field.
- Root cause: internal truthful semantic outcomes were designed without an
  explicit compatibility boundary at the existing public operation envelope.
- Required correction: retain the existing lifecycle status algebra and add a
  typed semantic-ingestion result reference. Define exact mapping: a durably
  recorded truthful terminal semantic result maps to committed lifecycle
  status, while only inability to durably record a truthful result maps to
  failed. Pending/running have no terminal semantic result. Bind legacy
  abstention and cutover behavior explicitly.
- Independent verification: exhaustive cross-product contract tests, old-
  reader compatibility, mixed-version serialization, status/result mismatch
  rejection, retryability, and cutover tests.

### DREV-031: Event identity is not bound to compiler record identity

- Severity: Medium / P2
- Governing requirement: SIA-R04 and SIA-R10
- Evidence: graph deltas use `(record_kind, record_id)`, while events and replay
  use `(record_kind, entity_id)`, with no normative mapping between the two.
- Root cause: the generic event-model field name was retained without an
  adapter invariant at event construction and replay.
- Required correction: require `SemanticMemoryEventPayload.entity_id` to equal
  the originating `GraphRecordChange.record_id` for every record kind and
  validate that equality in event construction, delta/event bijection, replay,
  dedupe, and checkpoint paths.
- Independent verification: exhaustive record-kind round trips and mutations
  that substitute either identity while preserving every digest coordinate.

## Rejected Findings

- Missing target implementation and coverage ledger: rejected as a design
  finding. `$review-design` says not to reject a design merely because
  implementation work is substantial. The design already requires a future
  implementation coverage ledger and cutover evidence.
- Current tests do not execute all target controls: rejected for the same
  reason. Existing tests are repository-reality evidence, not proof that an
  unimplemented target architecture is defective.
- Broader retrieval, language, or agent changes: rejected as outside scope.

## Outcome

`Changes required`. Resolve DREV-028 through DREV-031 with one writer, freeze a
new baseline, and run a fresh full review using new reviewer instances.
