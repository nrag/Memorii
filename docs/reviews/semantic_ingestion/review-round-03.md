# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-03`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `cb776d08a469bf3c5f2930318301466986109c7e32418d09883802ef01be30aa`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Boyle`), correctness lane
  (`Ramanujan`), dedicated `test_reviewer` (`Cicero`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and production
  implementation remain excluded

Fresh reviewer instances inspected the complete frozen revision-02 design,
governing documents, relevant implementation, tests, and active WorkPlans. No
reviewer saw another lane's findings before completing. The coordinator
validated every proposed finding directly against repository evidence.

## Executive Assessment

Revision 02 closes DREV-016 through DREV-022. Normal production composition,
lease recovery, record-version ownership, observation-cohort independence, and
filesystem atomicity are now represented in the architecture.

Approval remains blocked by three P1 and two P2 findings, all within the
canonical event and traceability contracts. The event envelope lacks the
required deduplication identity, schema evolution is fail-closed without a
supported compatibility path, and signed mid-stream checkpoints are not typed.
The C12 requirement was also broadened beyond its governing filesystem scope,
and SIA-R09 retains one non-governing rationale label as a source.

## Confirmed Findings

### DREV-023: Event schema evolution has no compatibility contract

- Severity: High / P1
- Governing requirement: SIA-R10; canonical event model schema-versioning and
  replay requirements
- Evidence: `SemanticMemoryEvent` carries a free-form `schema_version` and
  replay rejects unknown versions, but the design defines no supported read
  versions, canonical decoder/upcaster, compatibility lifecycle, or mixed-
  version replay behavior.
- Root cause: fail-closed version validation was specified without the
  complementary compatibility mechanism required for durable historical
  events.
- Impact: an ordinary event-schema upgrade can make previously committed state
  unreplayable or force implementers to invent migration semantics.
- Required correction: define an explicit active schema registry, current
  write version, supported historical read versions, deterministic decode and
  upcast rules, retirement/migration rules, and registry-bound checkpoints.
- Completion evidence: prior-version, mixed-version, checkpoint-resume,
  retired-version, future-version, corrupt-envelope, and deterministic-upcast
  tests.

### DREV-024: C12 is broadened beyond the filesystem memory plane

- Severity: High / P1
- Governing requirement: engineering-hardening closure matrix C12
- Evidence: C12 requires process-safe, crash-atomic filesystem memory-plane
  commits. SIA-R21 and several derivative clauses require the same real-process
  crash/reopen conformance from every supported backend.
- Root cause: revision 02 generalized a backend-specific hardening requirement
  while propagating it through the design.
- Impact: the design creates unsupported obligations for non-durable or
  in-memory adapters and expands the frozen ingestion scope.
- Required correction: scope SIA-R21 and every derivative real-process
  crash/reopen requirement to the filesystem/JSONL memory-plane backend while
  retaining the abstract all-or-none transaction protocol for adapters that
  support semantic ingestion.
- Completion evidence: static cross-section consistency plus filesystem
  multiprocess, crash, reopen, corruption, and retry conformance.

### DREV-025: SIA-R09 cites a non-normative rationale label as a source

- Severity: Medium / P2
- Governing requirement: `.agent/PLANS.md` traceability contract and the
  design's sole-normative-namespace rule
- Evidence: SIA-R09 lists `ING-P1-19` in its source column even though the
  design declares CFP/ING identifiers non-normative rationale labels.
- Root cause: one historical review label remained after the revision-02
  namespace cleanup.
- Impact: future implementation plans can mistake an internal finding label for
  governing product authority.
- Required correction: cite only stable governing documents in SIA-R09 and
  retain `ING-P1-19` solely in the rationale-to-SIA mapping.
- Completion evidence: static audit proving no normative SIA source depends on
  CFP/ING labels.

### DREV-026: Canonical memory events omit the required dedupe key

- Severity: High / P1
- Governing requirement: SIA-R10; Memorii specification Section 18.2 event
  requirements and Section 18.3 idempotency
- Evidence: the governing event contract requires every event to carry a
  dedupe key. `SemanticMemoryEvent` has an `event_id` but no `dedupe_key`; prose
  mentions processed-event idempotency keys without defining their typed
  relationship to an event.
- Root cause: event identity and delivery-retry identity were conflated even
  though operation fences can change across retries.
- Impact: retries and restarts can duplicate committed state or use
  incompatible backend-specific deduplication semantics.
- Required correction: add a canonical logical-mutation dedupe key independent
  of attempt/fence identity, define the stored key-to-event binding, and make
  identical duplicates no-ops while treating same-key/different-content as
  corruption.
- Completion evidence: same-attempt duplicate, new-fence retry, restart,
  conflicting-same-key, and atomic key/event/state tests.

### DREV-027: Signed semantic replay checkpoints are implementation-defined

- Severity: Medium / P2
- Governing requirement: SIA-R10 and canonical event model checkpoint
  integration
- Evidence: the design requires signed mid-stream replay but defines no typed
  checkpoint schema, snapshot scope, watermark semantics, authority policy, or
  anti-rollback validation.
- Root cause: a generic checkpoint concept was referenced without specializing
  it for the semantic memory event stream.
- Impact: implementations can resume from incomplete, stale, cross-repository,
  or untrusted state while claiming checkpoint conformance.
- Required correction: define one typed replay-checkpoint artifact binding the
  complete materialized memory snapshot, graph revision, event watermark,
  writer epoch, event batch/delta, schema registry, signing authority, and
  trust policy; define exact validation and resume rules.
- Completion evidence: valid resume, genesis replay, snapshot mutation,
  watermark substitution, cross-repository replay, key lifecycle, rollback,
  mixed-version, and stale-registry tests.

## Rejected Findings

- Missing normal composition: rejected; SIA-R19 binds ordinary provider and
  filesystem builders to the certified Steps 1-8 path.
- Missing lease ownership and recovery: rejected; SIA-R20 defines renewable
  ownership, token/epoch fencing, bounded recovery, and terminal exhaustion.
- Missing oracle independence: rejected; the design separates pre-ingest
  expected semantics from direct structural observation and mutation-tests the
  comparator boundary.
- Missing semantic-group atomicity: rejected; the plan, authorization, delta,
  event batch, idempotency bindings, outcome, and graph revision are one
  commit boundary.
- General language or retrieval expansion: rejected as outside the frozen
  ingestion architecture scope.

## Outcome

`Changes required`. Resolve DREV-023 through DREV-027 with the smallest
complete corrections, freeze revision 03, and run a fresh full-design review
with new reviewer instances. This is the final permitted revision round.
