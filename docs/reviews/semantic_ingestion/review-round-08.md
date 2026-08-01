# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-08`
- Review mode: `full`
- Review outcome: `Not approved; revision budget exhausted`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `51aba79c1bce4ca2ac15dbccfd6b5a1f9c8d633a923fcd35715f5b4082b478c2`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Russell`), correctness lane
  (`McClintock`), dedicated `test_reviewer` (`Pasteur`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign and agent
  integration remain excluded

The dedicated `spec_auditor` and `correctness_reviewer` roles failed before
repository access because their fixed `gpt-5.6` model is unavailable for this
account. Fresh `gpt-5.4` high-reasoning agents executed those exact independent
mandates. The dedicated `test_reviewer` ran normally. All three reviewed the
complete frozen design without reading prior reports or another lane's
findings.

## Executive Assessment

Revision 06 resolves DREV-037 through DREV-041. The fresh whole-design review
found three high and four medium gaps. The design still leaves material choices
at the default proposer, event-mutation, source/operation atomicity, and
provider-normalization boundaries. It also lacks complete C11 replay,
redaction-behavior, and deterministic filesystem-interleaving verification.

The design is not approved. The newly authorized three-revision budget is
exhausted, so no fourth revision was made.

## Reconstructed Requirement Coverage

| Requirement area | Coverage | Finding |
| --- | --- | --- |
| Network-free default production composition | Incomplete | DREV-042 |
| Canonical delta-to-event operation mapping | Contradictory | DREV-043 |
| Atomic source admission and pending operation | Incomplete | DREV-044 |
| Existing provider ingress normalization | Incomplete | DREV-045 |
| Public delivery ID and partial-turn replay | Partial | DREV-046 |
| Valid-policy prompt redaction behavior | Partial | DREV-047 |
| Deterministic filesystem publication schedules | Partial | DREV-048 |
| Source admission and retention failure | Complete | None |
| Attribution bearer derivation | Complete | None |
| Production time attestation / acceptance witness ownership | Complete | None |
| Closed execution-stage algebra | Complete | None |
| Expected operation-introduction comparison | Complete | None |

## Confirmed Findings

### DREV-042: The ordinary default proposer is not normatively network-free

- Severity: High / P1
- Governing requirement: `memorii_storage_details.md` Section 7; SIA-R08
- Evidence: SIA-R08 proves only that a no-network deployment *can* promote, and
  the workflow permits a local or remote capability without selecting the
  ordinary default. The production builders are required to construct the
  pipeline but not to select a local, network-free default.
- Root cause: capability flexibility was specified without separately fixing
  default composition.
- Impact: an implementer must choose whether default startup is local,
  evidence-only, or remote. A remote choice violates the local-first and
  explicit-configuration requirements.
- Required correction: make ordinary in-memory and filesystem production
  builders select a network-free local capability by default. Remote proposal
  requires explicit operator configuration and the existing exact source-bound
  egress authorization; lack of either never silently changes proposer.
- Independent verification: default-constructor tests run with network denied
  and promote the supported local envelope; explicit remote opt-in tests prove
  default configuration makes zero remote calls.

### DREV-043: Delta-to-event mutation operation is undefined

- Severity: High / P1
- Governing requirement: canonical event model Sections 3-5; SIA-R10
- Evidence: `GraphRecordChange` exposes only `change_kind="update"`, while
  `SemanticMemoryEventPayload.operation` permits
  `create|update|link|unlink|version`; event and dedupe identities depend on
  change kind. No closed mapping selects one event operation from the delta.
- Root cause: append-only full-state graph changes were narrowed without
  narrowing or mapping the richer event operation algebra.
- Impact: independent writers can emit different operations and identities for
  the same delta, breaking deterministic replay and idempotency.
- Required correction: choose one closed rule. The smallest is to derive
  `create` exactly when `before_record_version` and `before_digest` are null and
  `update` otherwise, including logical retirement/invalidation, and remove
  unused event operations from this writer. Alternatively, carry a canonical
  mutation enum in the compiler delta. Event ID, dedupe key, payload, and replay
  must consume that same typed value.
- Independent verification: two independent derivations from the serialized
  delta produce identical operation, event ID, and dedupe key for creation,
  ordinary update, and logical retirement; every operation substitution fails.

### DREV-044: Accepted source and pending operation can be torn apart

- Severity: High / P1
- Governing requirements: SIA-R01, SIA-R20, and the existing operation lifecycle
- Evidence: Step 1 atomically persists the source and retention attestation,
  while Section 3.21 requires every accepted delivery to create one pending
  operation. The acceptance contract does not place that operation in the same
  transaction or define a durable accepted-but-unstarted queue.
- Root cause: source admission and work admission have separate durability
  models even though lease recovery assumes their one-to-one existence.
- Impact: a crash can leave a durably accepted source with no enumerable,
  reclaimable operation.
- Required correction: atomically persist the source observation, retention
  attestation, and initial `PendingSemanticOperation` under one delivery fence.
  The admission result binds all three digests. A durable alternative queue
  would be valid only if fully specified with enumeration and one-way
  idempotent promotion, but adds unnecessary state.
- Independent verification: crash at every write/publication/acknowledgement
  point and prove each accepted source has exactly one restart-recoverable
  pending or later operation, while no rejected or retry-required admission
  creates work.

### DREV-045: Existing provider hooks have no authoritative internal normalization

- Severity: Medium / P2
- Governing requirements: C3 normal production composition; SIA-R19/SIA-R22
- Evidence: Step 1 introduces a new source-admission `ProviderEvent` shape, but
  the current public `ProviderEvent` and Hermes hooks expose operation, content,
  role, target/action, session/task/user, timestamp, language, and modality.
  The design does not map those existing fields to source kind, original text,
  requested scope, and provenance.
- Root cause: the internal source contract reused the public type name and
  skipped the normalization boundary.
- Impact: implementation must invent scope, source-kind, text, and provenance
  semantics or change the public provider API, risking C3 and lifecycle
  compatibility.
- Required correction: preserve the current provider-facing API and rename the
  internal type to `SourceAdmissionRequest`. Define one typed, server-owned
  normalizer per existing provider operation/hook, including deterministic
  child event identity and authoritative derivation of source kind, content,
  requested scope, modality, and provenance. Callers gain no new authority.
- Independent verification: current hooks alone produce exact admission
  requests for user/assistant turn, session end, pre-compress, memory write, and
  delegation, with no new caller fields and unchanged replay/result behavior.

### DREV-046: C11 delivery and partial-turn replay semantics are incomplete

- Severity: Medium / P2
- Governing requirement: engineering-hardening closure matrix C11
- Evidence: Step 1 requires a retry-stable string delivery ID but does not
  explicitly reject blank normalized IDs, define deterministic child IDs for a
  composite hook, or require restart and partial-child replay.
- Root cause: the adapter fan-out boundary was clarified without carrying its
  existing identity/recovery invariants into normative acceptance.
- Impact: C11 remains unverifiable and implementers can choose incompatible
  child identity or partial-recovery behavior.
- Required correction: add C11 to a stable SIA requirement. Require non-empty
  normalized caller IDs at every public mutation, deterministic domain-separated
  child IDs, exact reuse across restarts, and partial-turn replay that processes
  only missing children without duplicate source or graph effects.
- Independent verification: blank-ID public API tests, child-ID determinism,
  cross-process replay, conflicting replay, and each partial-child recovery
  permutation through the provider boundary.

### DREV-047: Valid prompt redaction behavior is not verified

- Severity: Medium / P2
- Governing requirements: prompt contract security boundary; SIA-R07
- Evidence: prompt tests mutate redaction/visibility registrations and block
  mismatches, but do not prove that a valid policy removes nested secrets from
  rendered prompts, provider payloads, and traces.
- Root cause: registration integrity and policy execution were tested as one
  property.
- Impact: a correctly registered but incorrectly executed redactor can disclose
  source secrets while all declared tests pass.
- Required correction: add valid-policy fake-transport tests over nested
  mappings and sequences. Assert only redacted values reach rendered prompt,
  request, and trace, raw values occur nowhere, and mutation of caller inputs
  after sanitization cannot reintroduce them.
- Independent verification: an observer separate from the renderer inspects
  serialized transport and persisted trace bytes; policy/digest mutation tests
  remain as a separate negative layer.

### DREV-048: Filesystem atomicity lacks deterministic interleaving verification

- Severity: Medium / P2
- Governing requirements: C12; SIA-R21
- Evidence: the real-process suite names concurrency, crash, replacement, and
  reader outcomes but does not define controllable publication points or a
  finite writer/reader schedule matrix.
- Root cause: outcome coverage was specified without schedule coverage.
- Impact: timing-based tests can miss the publication race or become flaky
  while still claiming process-safe atomicity.
- Required correction: the test harness, without adding test concepts to
  production contracts, controls processes at observable filesystem operation
  boundaries: before staging write, before atomic replace, after replace before
  acknowledgement, and before/after reader snapshot validation. Execute a fixed
  same-delivery, distinct-delivery, reader/writer, crash, reopen, and recovery
  schedule matrix.
- Independent verification: every reader sees the exact prior generation or
  one checksum-valid complete new generation; same-delivery writers yield one
  effect; distinct writers serialize or return the declared conflict; crash and
  reopen release recovery without partial visibility.

## Coordinator Disposition

All seven findings are confirmed by direct design, governing-source, production
code, or test evidence. DREV-045 and DREV-046 do not add agent integration:
they preserve the already-supported provider boundary and its current
multi-event hook semantics. DREV-048 explicitly keeps process orchestration in
the test harness rather than adding test-only contracts to production.

No retrieval/query redesign, provider migration, compatibility version, or
unrelated cleanup is required.

## Unresolved-Findings Decision

The workflow does not converge within the authorized three-revision cycle.
Approval requires an external decision to authorize one additional bounded
revision containing only DREV-042 through DREV-048 and their direct consistency
updates. That revision must:

1. fix the network-free ordinary default;
2. close delta-to-event operation derivation;
3. atomically bind source admission to pending work;
4. define current-provider-to-admission normalization and C11 replay;
5. add valid-policy redaction verification; and
6. add deterministic filesystem interleaving verification without production
   test hooks.

Without that authorization, the design remains not approved and no
implementation should claim these contracts are complete.

## Outcome

`Not approved; revision budget exhausted`. Three high and four medium findings
remain. No fourth design revision was performed.
