# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-round-09`
- Review mode: `full`
- Review outcome: `Changes required`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline: SHA-256
  `51aba79c1bce4ca2ac15dbccfd6b5a1f9c8d633a923fcd35715f5b4082b478c2`
- Implementation baseline: `f76850fc45f09d21a40b5a7302d173ce642ec9d6`
- Review date: 2026-07-26
- Reviewers: independent spec-audit lane (`Parfit`), correctness lane
  (`Pauli`), dedicated `test_reviewer` (`Singer`), coordinator validation
- Scope: complete semantic-ingestion design; retrieval redesign, agent
  integration, production implementation, and unrelated cleanup remain excluded

This report continues the immutable report sequence after round 08. The user
authorized a fresh budget of at most three revisions to close the seven round-08
findings. All three lanes independently reviewed the complete unchanged design
before consulting prior reports. The dedicated `spec_auditor` and
`correctness_reviewer` role launches failed before repository access because
their fixed model was unavailable; fresh high-reasoning agents executed those
same read-only mandates. The dedicated `test_reviewer` ran normally.

## Executive Assessment

The design remains not approved. Five high and eight medium findings are
confirmed. Seven carry forward the unresolved round-08 inventory. Six are new
whole-design defects exposed by independently reviewing capability authority,
dependency topology, temporal inputs, source-result finality, and terminal
lease semantics.

The findings remain inside semantic-ingestion architecture. They do not require
retrieval redesign, agent integration, compatibility APIs, or implementation
changes in this operation.

## Reconstructed Requirement Coverage

| Requirement area | Coverage | Finding |
| --- | --- | --- |
| Network-free ordinary production default | Incomplete | DREV-042 |
| Canonical graph-mutation to event mapping | Contradictory | DREV-043 |
| Atomic admission, graph/control commit, and finalization | Incomplete | DREV-044 |
| Existing provider ingress normalization | Incomplete | DREV-045 |
| C11 delivery identity and partial-child replay | Partial | DREV-046 |
| Valid redaction-policy execution evidence | Partial | DREV-047 |
| Deterministic filesystem interleaving evidence | Partial | DREV-048 |
| Proposal authority versus operation certification | Contradictory | DREV-049 |
| Initial dependency and deployment topology | Partial | DREV-050 |
| Typed temporal-policy input to normalization | Missing | DREV-051 |
| Closed effective-time representation | Contradictory | DREV-052 |
| Retryable group failure versus terminal partial commit | Contradictory | DREV-053 |
| Lease-exhaustion semantic result | Missing | DREV-054 |

## Confirmed Findings

### DREV-042: The ordinary default proposer is not normatively network-free

- Severity: High / P1
- Requirement: storage-details local-first behavior; SIA-R08 and SIA-R19
- Evidence: the design permits local or remote certified proposers but never
  fixes the ordinary in-memory/filesystem constructor default.
- Root cause: capability flexibility and default composition are conflated.
- Required correction: ordinary builders select a certified local, network-free
  proposal capability. Remote proposal requires explicit operator selection and
  exact active egress authorization; no outage or configuration error switches
  proposer implicitly.
- Completion evidence: constructor tests with network denied promote the local
  supported envelope; remote transport observes zero calls without explicit
  selection and valid authorization.

### DREV-043: Delta-to-event mutation operation is undefined

- Severity: High / P1
- Requirement: canonical event model Sections 3-5; SIA-R10
- Evidence: `GraphRecordChange` exposes only `change_kind="update"`, while the
  event payload admits `create|update|link|unlink|version`; event identity and
  dedupe depend on the operation.
- Root cause: the graph-change algebra was narrowed without narrowing the event
  algebra or defining a total mapping.
- Required correction: carry one closed `create|update` mutation kind in every
  graph mutation. Creation has no before version/digest and starts at version
  one; update has both and advances the prior version. Logical retirement is an
  update. Event payload, event ID, dedupe key, and replay consume that exact
  value; unused operations are forbidden for this writer.
- Completion evidence: independent derivation from serialized mutations agrees
  for create, update, and retirement, and every substitution fails.

### DREV-044: Semantic ingestion lacks an explicit atomic storage contract

- Severity: High / P1
- Requirements: SIA-R01, SIA-R20, SIA-R21, SIA-R22; C12 and C13
- Evidence: Step 1 atomically stores source plus retention attestation but not
  the mandatory pending operation. Later prose requires atomic graph batches
  and source finalization while saying to reuse transaction primitives that do
  not express mixed graph/control CAS, lease, writer epoch, and result rows.
- Root cause: three authoritative durability boundaries are described as
  outcomes without one implementable storage protocol or exact revision/CAS
  domains.
- Required correction: define one semantic-ingestion atomic-store protocol
  with typed source-admission, committed-group, and source-finalization writes.
  Each request names exact preconditions, read sets, lease/writer fences,
  visible records, idempotency behavior, and backend conformance. Admission
  atomically creates source, retention attestation, and pending operation.
- Completion evidence: in-memory and filesystem conformance proves all-or-none
  visibility and deterministic retry at every write, replace, CAS, and lost-ack
  boundary without nested units of work.

### DREV-045: Existing provider hooks have no authoritative normalization

- Severity: Medium / P2
- Requirements: C3; SIA-R19 and SIA-R22
- Evidence: Step 1 reuses `ProviderEvent` for a new internal shape, while the
  current public event exposes operation, content, role, target/action,
  session/task/user, timestamp, language, and modality.
- Root cause: the public adapter contract and internal admission contract were
  collapsed without a total server-owned mapping.
- Required correction: preserve the public API, name the internal contract
  `SourceAdmissionRequest`, and define a typed normalizer for every current
  provider operation/hook. Scope, source kind, provenance, and child delivery
  identity are server-owned derivations.
- Completion evidence: every existing hook produces an exact admission request
  with no new caller authority and unchanged provider lifecycle serialization.

### DREV-046: C11 delivery and partial-turn replay semantics are incomplete

- Severity: Medium / P2
- Requirement: engineering-hardening closure matrix C11
- Evidence: the design does not normatively reject normalized blank IDs, define
  child IDs for composite hooks, or require restart/partial-child recovery.
- Root cause: provider fan-out identity was left implicit at the adapter edge.
- Required correction: add one stable SIA requirement for nonblank public
  delivery IDs, deterministic domain-separated child IDs, restart identity,
  and replay that executes only missing children.
- Completion evidence: blank, collision, restart, conflicting replay, and every
  partial-child permutation pass through the ordinary provider boundary.

### DREV-047: Valid prompt-redaction execution is not verified

- Severity: Medium / P2
- Requirements: prompt security boundary; SIA-R07
- Evidence: verification mutates registrations but does not prove a valid
  registered policy removes nested secrets from prompt, transport, and traces.
- Root cause: policy registration integrity and policy execution were treated
  as one property.
- Required correction: specify independent serialized-byte observation over
  nested mappings/sequences and immutable sanitized copies.
- Completion evidence: valid-policy tests find only redacted values in rendered
  prompt, request, and trace; post-sanitization caller mutation cannot restore
  raw values.

### DREV-048: Filesystem atomicity lacks deterministic schedule coverage

- Severity: Medium / P2
- Requirements: C12; SIA-R21
- Evidence: tests name process concurrency and crash outcomes but define no
  controllable publication boundaries or finite interleaving matrix.
- Root cause: outcome coverage is specified without schedule coverage.
- Required correction: a test-only process coordinator wraps the existing
  filesystem boundary at before-stage, before-replace, after-replace/before-ack,
  and reader snapshot-validation points. Production contracts gain no test hook.
- Completion evidence: a fixed writer/writer, writer/reader, crash, reopen, and
  recovery schedule matrix observes only the prior or complete new generation.

### DREV-049: Proposal authority and per-operation certification conflict

- Severity: High / P1
- Requirements: SIA-R03, SIA-R05, SIA-R08; prompt registration and typed-owner
  rules
- Evidence: `CertifiedSemanticCapability` simultaneously selects the Step 3
  proposer/prompt/schema before operation interpretation and later authorizes a
  predicate/construction-specific operation after alignment.
- Root cause: segment-level generative execution and operation-level semantic
  promotion use one capability identity despite having different selection
  times and ownership.
- Required correction: define a segment-level certified proposal capability and
  a separate per-operation certified semantic capability. Proposal artifacts
  bind the exact proposal capability that ran. Each semantic capability declares
  compatibility with that proposal capability and is selected only after typed
  operation evidence exists. No hidden pre-proposal semantic routing is allowed.
- Completion evidence: a mixed-family segment proves every accepted operation
  is authorized by a compatible per-operation capability while retaining the
  exact proposer/prompt/schema provenance that actually executed.

### DREV-050: The initial deployment dependency topology is incomplete

- Severity: Medium / P2
- Requirement: SIA-R16 and local-first deployment
- Evidence: Section 3.12's dependency extra omits required fastText, PyICU,
  Duckling runtime/client, and the optional remote OpenAI adapter named by the
  module and rollout sections.
- Root cause: an illustrative package list is acting as the deployment source
  of truth.
- Required correction: define one authoritative deployment manifest covering
  Python distributions, model/tokenizer assets, local external runtimes,
  checksums/licenses, and explicitly optional remote adapters. Packaging,
  certification, modules, and rollout reference only that manifest.
- Completion evidence: a static audit proves every mandatory runtime/module has
  one manifest entry and every packaged entry has an owning runtime consumer.

### DREV-051: Step 5 lacks its typed temporal-policy authority

- Severity: Medium / P2
- Requirements: SIA-R04 and SIA-R12
- Evidence: normalization applies a closed temporal policy, but
  `EvidenceNormalizationRequest` carries no `TemporalPolicySnapshot` or
  equivalent typed rule content.
- Root cause: a policy fingerprint is recorded downstream while the policy
  content is obtained through an unstated lookup.
- Required correction: carry the selected immutable temporal-policy snapshot in
  Step 5 and bind its digest through every dependent assessment and artifact.
- Completion evidence: holding all other inputs fixed and changing only the
  snapshot changes output only through the typed request; live policy lookup is
  forbidden.

### DREV-052: Effective-time encoding is internally contradictory

- Severity: Medium / P2
- Requirement: SIA-R12 and closed persisted algebras
- Evidence: the schema defines discriminated `EffectiveTimeCoordinate`, but
  prose still instructs `effective_at is None` for system-recorded time.
- Root cause: stale nullable semantics survived the union conversion.
- Required correction: retain only `SystemRecordedEffectiveTime`; remove every
  nullable alternate representation.
- Completion evidence: exhaustive variant round trips pass and malformed
  nullable rows fail.

### DREV-053: Retryable group failure can become terminal partial commit

- Severity: High / P1
- Requirements: SIA-R01, SIA-R20, SIA-R22
- Evidence: `partially_committed` permits a failed group and maps the source to
  terminal `evolution_committed`, `retryable=false`.
- Root cause: deterministic semantic non-commit and retryable infrastructure
  failure share one terminal source-result lattice.
- Required correction: source finalization is forbidden while any group has a
  retryable failure. Durable progress records committed groups; replay of the
  same operation resumes only unfinished groups. `partially_committed` is
  terminal only when every noncommitted group has a deterministic terminal
  semantic disposition.
- Completion evidence: after group A commits and group B conflicts/crashes, no
  committed coarse lifecycle is visible; restart resumes B without repeating A.

### DREV-054: Lease-recovery exhaustion has no semantic-result mapping

- Severity: Medium / P2
- Requirements: SIA-R20 and SIA-R22
- Evidence: the terminal operation union includes
  `lease_recovery_exhausted`, but `SourceIngestionResult` and provider mapping do
  not preserve it.
- Root cause: operation-state and semantic-result terminal algebras diverged.
- Required correction: represent exhaustion as a typed terminal failed reason,
  map it to coarse `evolution_failed`, `retryable=false`, and preserve the same
  reason through the semantic accessor and replay.
- Completion evidence: fake-clock stale recovery exhausts exactly at the bound
  and round-trips the reason through operation, semantic result, and coarse
  provider lifecycle.

## Rejected And Consolidated Reviewer Proposals

- The test reviewer reported that current production tests do not yet implement
  most SIA-R evidence. Those are implementation-plan obligations, not defects in
  a design that already specifies the required evidence. They are unsupported
  as new design findings and must not cause the document to claim unimplemented
  code exists.
- The redaction and deterministic-interleaving proposals are retained as
  DREV-047 and DREV-048 because the design's verification strategy itself is
  incomplete.
- The correctness review's mixed control/data transaction finding is
  consolidated into DREV-044. Splitting source admission from graph/control
  commit would leave the same storage-boundary root cause fragmented.

## Revision Scope

The frozen revision inventory is DREV-042 through DREV-054 only. Direct
consistency updates to schemas, workflow, rollout, risk, traceability, and
acceptance are included. Retrieval/query behavior, agent integration,
production code, test implementation, compatibility layers, and unrelated
cleanup are excluded.

## Outcome

`Changes required`. Five high and eight medium findings block approval. One
coherent bounded revision is authorized before freezing a new baseline and
starting a fresh full independent review.
