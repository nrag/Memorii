# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-13`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `da450ce335ce8caad62c9496a5a4dd690803907186437f81a05c080012daeeaf`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: dedicated `spec_auditor` (`Plato`), dedicated
  `correctness_reviewer` (`Schrodinger`), dedicated `test_reviewer`
  (`Lagrange`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign, production
  implementation, agent integration, and unrelated cleanup remain excluded

Existing reports 01-12 are immutable. The user-requested new initial review is
therefore recorded as round 13 rather than overwriting round 01. All reviewers
read the complete frozen design and were instructed not to read prior reports.

## Executive Assessment

The design is not approved. The coordinator validates three P1 and four P2
findings. The spec lane approved, but the correctness and verification lanes
found concrete contradictions or missing contracts. Coordinator inspection of
the governing requirements, provider models, generic memory-plane store, and
legacy evolution path confirmed the complete inventory below.

These findings are all direct violations of existing SIA requirements and stay
inside semantic ingestion. They do not authorize retrieval redesign, production
implementation, compatibility versions, or agent integration.

## Confirmed P1 Findings

### DREV-067: Writer admission does not fence the common semantic-write boundary

- Severity: P1 / Blocking
- Requirements: SIA-R11, SIA-R19, SIA-R20, and SIA-R21
- Evidence: `SemanticWriterCommitBinding` is required only on transaction-group
  CAS. Admission, checkpoint, and finalization requests omit it. The current
  generic `MemoryPlaneStore.apply_batch` and legacy evolution path accept
  semantic records with only revision/record preconditions, so an old process
  can bypass the target coordinator after cutover.
- Reproduction: pause an old process after lease acquisition, advance writer
  admission in another process, then release the old generic write. Its ordinary
  revision and record fence can still pass. Target checkpoint/finalization also
  have no modeled writer-admission comparison.
- Root cause: writer authority was attached to target graph-group commits rather
  than to every semantic record mutation at the shared storage boundary.
- Required correction: define a non-optional writer binding for admission,
  checkpoint, terminal-group, finalization, and every generic semantic record
  mutation; bind admitted operations to the writer epoch; define a pre-cutover
  legacy admission mode that becomes invalid atomically; and drain or
  terminalize old-epoch operations before activation.
- Independent verification: two real processes prove that stale legacy generic
  writes and stale target writes at every boundary fail after activation or
  rollback with no graph/event/observation/artifact/lifecycle revision change.

### DREV-068: Temporal-reference provenance is not closed across source, resolver, durable, and oracle contracts

- Severity: P1 / Blocking
- Requirements: SIA-R04, SIA-R06, SIA-R12, SIA-R17, and SIA-R18
- Evidence: `SourceSemanticContext` distinguishes event and authenticated
  document time, the resolver uses different basis literals, and downstream
  accepted/effective-time contracts preserve only an event-time variant. A
  relative expression resolved from document time has no total durable or
  expected/observed representation.
- Reproduction: resolve identical relative text once against authenticated
  event time and once against authenticated document time. Equal timestamps can
  collapse despite distinct provenance, and document-time evidence cannot be
  represented by the effective-time union without invention.
- Root cause: temporal reference values were threaded as timestamps and ad hoc
  basis strings instead of one discriminated evidence identity.
- Required correction: define one closed `TemporalReferenceEvidence` union for
  event time and document time, bind source-context field/digest and provenance,
  and carry its identity through resolver input/output, accepted operation,
  effective-time coordinate, durable records, replay, expected graph, observed
  graph, and comparator. Reject every unmapped or mismatched combination.
- Independent verification: equal-value/different-basis mutations, missing or
  swapped source fields, restart/replay, relative expressions under both bases,
  and expected/observed comparison must preserve or reject provenance exactly.

### DREV-069: Stable allocation identity is conflated with renewable lease fencing

- Severity: P1 / Blocking
- Requirements: SIA-R04, SIA-R10, SIA-R20, and SIA-R21
- Evidence: planned entity/action IDs are derived from an “operation fence,”
  while stale recovery changes `execution_token` and `ownership_epoch`.
  `operation_fence_id` is not normatively defined as stable operation identity
  or renewable lease identity.
- Reproduction: crash after planning and reclaim before first commit. If the
  fence follows the new lease, planned IDs change; if it follows the old lease,
  stale-owner fencing is ineffective.
- Root cause: idempotent allocation namespace and mutable write authorization
  were represented by one ambiguous term.
- Required correction: define a stable `allocation_namespace_id` derived from
  normalized delivery and immutable operation ID for deterministic IDs, and a
  separate current `OperationLeaseBinding` for write authorization. Persist and
  compare both; lease recovery preserves allocation IDs while rejecting the old
  token/epoch.
- Independent verification: crash/reclaim before and after planning produces
  byte-identical reservations and IDs, stale owner writes fail, and conflicting
  delivery/operation identities cannot share a namespace.

## Confirmed P2 Findings

### DREV-070: Temporal-mode and evidence-precedence rules contradict SIA-R06

- Severity: P2 / Medium
- Requirements: SIA-R03, SIA-R06, SIA-R12, and SIA-R18
- Evidence: SIA-R06 says omitted temporal expressions cannot promote current or
  historical truth, while the detailed contract permits `optional` and
  `atemporal` predicates and authenticated source interval or event time without
  textual time. Only `required` explicitly rejects missing evidence.
- Root cause: proposer omission of source-present text, genuinely absent text,
  authenticated non-text evidence, ambiguity, and atemporal predicates were
  collapsed into one omission rule.
- Required correction: add one normative decision matrix crossing predicate
  temporal mode with certified text, authenticated interval, authenticated event
  time, authenticated document time, none, and ambiguous/misattached text.
  Revise SIA-R06 and all component prose to the same outcomes.
- Independent verification: table-driven tests cover every matrix cell,
  conflicting evidence, proposer omission, replay, and atemporal
  non-supersession.

### DREV-071: The preserved provider lifecycle wire contract is not immutably pinned

- Severity: P2 / Medium
- Requirements: SIA-R03 and SIA-R22
- Evidence: the design freezes only four lifecycle status literals while the
  current `ProviderEvolutionOutcome` also contains attempt, retry, failure,
  extraction, and fallback fields plus validation/default semantics. The design
  promises the same payload without naming an immutable complete baseline.
- Root cause: semantic lifecycle mapping was specified, but legacy wire
  compatibility remained ambient repository state.
- Required correction: identify the exact authoritative model and serializer at
  immutable revision/tree digest, include all fields/defaults/nullability/enums
  and validation semantics, declare an empty allowed change set, and bind
  compatibility evidence to independently captured fixtures.
- Independent verification: every lifecycle/failure/retry variant matches the
  pinned canonical JSON fixture; schema diff rejects added, removed, renamed,
  retyped, re-aliased, or default-changed fields and semantic fields on the old
  endpoint.

### DREV-072: Accepted admission cannot construct the lease-acquisition request

- Severity: P2 / Medium
- Requirements: SIA-R01, SIA-R04, SIA-R20, and SIA-R23
- Evidence: `admit_source` persists a `PendingSemanticOperation` containing
  `operation_id`, but `SourceAdmissionAccepted` returns only its digest and no
  typed delivery-index lookup is defined.
- Root cause: the atomic admission write and execution handoff were designed
  independently.
- Required correction: return immutable operation ID, allocation namespace,
  writer epoch, and pending-operation digest in `SourceAdmissionAccepted`, or
  define one typed delivery-index lookup returning those coordinates. Matching
  replay returns the byte-identical handoff; conflicting replay fails.
- Independent verification: admission-to-lease, lost acknowledgement, restart,
  matching replay, conflicting replay, and stale-writer acquisition tests use no
  inferred IDs or side channels.

### DREV-073: Snapshot and delegation source bytes are not constructible from the preserved provider API

- Severity: P2 / Medium
- Requirements: SIA-R01, SIA-R03, SIA-R22, and SIA-R23
- Evidence: the design preserves the single-string `ProviderEvent.content`
  contract but says adapters serialize message collections for session snapshots
  and task/result collections for delegation. It defines no envelope schema,
  ordering, source references, version, or digest.
- Root cause: adapter-owned structured inputs were described as if the unchanged
  public event already carried them.
- Required correction: keep `ProviderEvent` unchanged and require adapters to
  produce one versioned canonical `ProviderSourceEnvelope` before normalization;
  define snapshot/delegation variants, ordering, required fields, canonical
  encoding, source/provenance references, limits, and fingerprint. `content` is
  the exact canonical serialized envelope for these operations and ordinary
  verbatim text for text operations.
- Independent verification: cross-adapter byte equality, message/task/result
  reorder mutations, duplicate/missing references, schema-version changes,
  size limits, replay, and old-provider compatibility.

## Reviewer Dispositions

- The spec lane approved. Coordinator evidence from the other two lanes and
  direct repository inspection overrides that advisory conclusion for the seven
  concrete contradictions above.
- The verification lane's temporal-reference and writer-fence reports were
  confirmed as DREV-067 and DREV-068; its lifecycle report was confirmed as
  DREV-071.
- The correctness lane's fence-identity, admission-handoff, and provider-input
  reports were confirmed as DREV-069, DREV-072, and DREV-073.
- The coordinator separately confirmed the requirement-level temporal-mode
  contradiction as DREV-070 rather than hiding it inside DREV-068. DREV-068
  closes provenance representation; DREV-070 closes semantic precedence.
- No implementation-absence finding was accepted. No retrieval or agent work
  was added.

## Approval Decision

**Changes required.** DREV-067 through DREV-073 form the frozen inventory for
revision 10. The smallest complete revision must resolve all seven findings and
their direct consistency consequences, then pass a fresh whole-design review.
