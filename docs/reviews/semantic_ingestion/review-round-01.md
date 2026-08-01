# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-2026-07-26-restart-round-01`
- Review mode: `full`
- Review outcome: `Blocked`
- Design path: `docs/design/semantic_ingestion_architecture.md`
- Design baseline SHA-256:
  `376a0d774bc951c5fd4190b165006f138c05f3145e9ad697d94b65f7760e3a17`
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Review date: 2026-07-26
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation
- Included scope: complete semantic-ingestion architecture and acceptance
  surface
- Excluded scope: query/retrieval redesign, implementation, agent integration,
  and unrelated cleanup

## Executive Assessment

The design remains strong on source-grounded proposal validation,
language-neutral reconciliation, deterministic compilation, graph atomicity,
replay artifacts, historical/trust/identity preservation, and an acceptance
oracle separated from production semantic helpers.

It is not implementation-ready. Coordinator validation confirms three P1
product defects, four P2 product defects, and three approval findings whose
product priority is `Not applicable`. The P1/P2 count follows the repository
taxonomy rather than legacy `Blocking/High/Medium` labels:

- P1 findings break the ordinary ingestion path or require every implementer to
  invent its core identity/security semantics.
- P2 findings affect important replay, governance, concurrency, and release
  paths while leaving the ordinary happy path conceptually intact.
- `Not applicable` findings are external decisions or evidence-governance gaps
  that block approval without a demonstrated product-incidence percentage.

Seven findings have determinate design corrections. Three require an external
owner decision or approved artifact and cannot be invented by the design
writer.

## Governing Sources

Precedence follows `AGENTS.md`:

1. `docs/design/memorii_spec.md`
2. `docs/design/memorii_storage_details.md`
3. `docs/design/event_model.md`
4. `docs/IMPLEMENTATION_RULES.md`
5. `docs/design/semantic_ingestion_architecture.md`
6. `docs/plans/engineering_hardening_closure_matrix.md`

## Confirmed Findings

### DREV-001: Foundational ingestion contracts are undefined or ambiguous

- Product priority: `P1`
- Approval disposition: `changes_required`
- Finding type: contract composition and persistence
- Affected scenario and prevalence evidence: every ordinary ingestion starts
  with `SourceAdmissionRequest` and carries source, span, provenance, and scope
  data through all semantic stages; this is the mainstream path.
- Design evidence: `SourceKind`, `SourceProvenance`, and `TextSpan` are used at
  lines 3036-3213 and throughout the pipeline but have no owned normative
  definitions. `MemoryScope` is also unqualified, while production has
  incompatible enum and structured-scope definitions in
  `memorii/memorii/domain/enums.py` and
  `memorii/memorii/core/memory_evolution/models.py`.
- Violated requirements: SIA-R01, SIA-R04, SIA-R12, SIA-R23; typed ownership
  and serialization rules in `docs/IMPLEMENTATION_RULES.md`.
- Root cause: the design specifies downstream behavior before choosing one
  canonical primitive-contract owner and encoding.
- Impact: implementers must invent Unicode span units, scope identity,
  provenance fields, serialization, digest inputs, and projection bindings.
  Independent implementations can authorize or replay different graphs.
- Smallest complete correction: add one normative primitive-contract section
  and owner module defining closed `SourceKind`, structured `SourceProvenance`,
  canonical `TextSpan`, and the ingestion `MemoryScope`; define encoding,
  half-open offset unit, source/projection binding, validation, digest, and
  relationship to existing production types.
- Verification: schema round trips, Unicode and normalization mutations,
  segment-boundary checks, scope-isolation checks, digest vectors, and a static
  ownership/import audit.

### DREV-002: Authenticated ingress has no ordinary production handoff

- Product priority: `P1`
- Approval disposition: `changes_required`
- Finding type: security and integration
- Affected scenario and prevalence evidence: all normal provider mutations use
  `ProviderMemoryService.sync_event`; this is the default ingestion entry point.
- Design evidence: lines 2144-2180 require an out-of-band
  `AuthenticatedIngressContext`, but define no resolver, issuer, trust
  mechanism, service injection point, or compatibility behavior.
- Repository evidence: `memorii/memorii/core/provider/service.py:154` accepts
  caller-supplied session/task/user identifiers; the production factory at
  `memorii/memorii/core/provider/factory.py:23` injects no ingress authority.
- Violated requirements: SIA-R01, SIA-R09, SIA-R19, SIA-R23.
- Root cause: the design introduced a trusted context data model without
  designing the authority boundary that creates it.
- Impact: the ordinary path must either trust caller fields, fabricate
  authentication, reject all traffic, or bypass the new contract.
- Smallest complete correction: define a framework-neutral
  `AuthenticatedIngressContextResolver` protocol, authenticated host input,
  issuer/trust policy, factory injection, adapter handoff, expiry/revocation,
  and fail-closed behavior for hosts that cannot provide trusted context.
- Verification: forged caller fields, two-principal same-ID, expired/revoked
  sessions, cross-tenant replay/recovery, missing resolver, and ordinary factory
  integration tests.

### DREV-003: The immutable operation fence is absent from the durable handoff

- Product priority: `P1`
- Approval disposition: `changes_required`
- Finding type: transaction, fencing, and replay
- Affected scenario and prevalence evidence: every accepted source creates an
  operation and every graph-bound or terminal result relies on its fence; this
  is the mainstream commit path.
- Design evidence: lines 2203-2213 promise an `operation_fence_id` across all
  state; `PendingSemanticOperation`, `ActiveSemanticOperationLease`,
  `TerminalSemanticOperation`, `OperationLeaseBinding`, and
  `SourceAdmissionAccepted` omit it. `SourceAdmissionAtomicWriteRequest` instead
  has an unrelated `delivery_fence_id` at line 7645.
- Violated requirements: SIA-R04, SIA-R10, SIA-R20, SIA-R21, SIA-R23.
- Root cause: prose introduced a stable operation identity without composing it
  into the admission and state algebra.
- Impact: recovery and persistence must recompute or look up an unstated fence;
  mismatched operations can be associated with the wrong events, artifacts, or
  terminal outcomes.
- Smallest complete correction: define one immutable
  `OperationFenceBinding`, create it atomically at admission, return and persist
  it in every operation/lease/checkpoint/group/finalization contract, and remove
  or normatively replace `delivery_fence_id`.
- Verification: admission/replay byte equality, lost acknowledgement, lease
  reclaim, cross-operation substitution, checkpoint/group/finalization fence
  mutation, and static field-closure checks.

### DREV-004: Equal-version replay semantics conflict

- Product priority: `P2`
- Approval disposition: `blocks_approval`
- Finding type: governance and replay correctness
- Affected scenario and prevalence evidence: divergent same-record/version
  events are not the dominant ingest path, but corruption recovery, historical
  replay, and checkpoint resume are important supported cases.
- Design evidence: SIA-R10 and lines 2137-2142 fail closed pending an external
  decision.
- Governing evidence: `docs/design/event_model.md:218-224` selects event-ID
  ordering, while lines 247-287 skip every same-version event.
- Root cause: the higher-precedence event model is internally contradictory.
- Impact: genesis and checkpoint-tail replay cannot have one governed outcome.
- Required external correction: the event-model owner must select one rule for
  exact duplicates, non-identical equal-version history, and current-writer
  collisions, then update the governing event model and this design.
- Verification: all arrival permutations from genesis and signed checkpoints,
  exact duplicates, upcasts, corruption, and mixed-version migration.

### DREV-005: Capability/profile approvals lack a verifiable trust lifecycle

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: security and release governance
- Affected scenario and prevalence evidence: capability activation and local
  profile rollout are important release paths, though not per-message behavior.
- Design evidence: `LocalExecutionResourceProfile` and
  `ApprovedCapabilityBaselineArtifact` at lines 2273-2312 carry an opaque
  `approval_evidence_digest` but no signed purpose, authority snapshot, active
  release, expiry, revocation, or use-time validation.
- Violated requirements: SIA-R13, SIA-R14, SIA-R16.
- Root cause: the design reused the word “approved” without composing these
  artifacts with its later lifecycle-checked acceptance release authority.
- Impact: stale, substituted, revoked, or arbitrary approval evidence can
  activate model behavior or resource limits.
- Smallest complete correction: bind both artifacts to the existing typed
  acceptance-release/trust lifecycle with signer, purpose, immutable authority
  snapshot, signature, active epoch, expiry/revocation, and use-time checks.
- Verification: reject unsigned, wrong-purpose, expired, revoked, superseded,
  substituted, and rollback artifacts before activation or admission.

### DREV-006: Local capacity admission has no atomic reservation semantics

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: concurrency, recovery, and operability
- Affected scenario and prevalence evidence: constrained local deployments and
  concurrent admissions are important supported conditions for the intended
  local-first path.
- Design evidence: lines 2273-2369 define counts and outcomes but no reservation
  identity, queue order, linearization point, lease/fence binding, release, or
  crash reclaim.
- Violated requirements: SIA-R08, SIA-R16, SIA-R20, SIA-R21.
- Root cause: capacity is modeled as configuration plus outcome labels rather
  than a process-safe state machine.
- Impact: implementations can oversubscribe the final slot, leak capacity after
  crashes, or produce nondeterministic retries.
- Smallest complete correction: add a store-owned local-admission reservation
  state tied to delivery key, operation fence, profile digest, server-clock
  deadlines, queue sequence, and terminal/recovery transitions.
- Verification: two-process final-slot race, duplicate retry, crash while
  reserved, queue/deadline races, deterministic reclaim, and zero semantic or
  graph effects for non-admitted sources.

### DREV-007: Egress activation permits transitions without mandatory CAS

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: security and concurrency
- Affected scenario and prevalence evidence: remote egress is optional, but
  policy rotation, revocation, and rollback are important confidentiality
  controls when enabled.
- Design evidence: `EgressGovernanceCommand.expected_active_record_digest` is
  nullable at line 2266; prose does not require atomic compare-and-set for every
  active-policy transition.
- Violated requirement: SIA-R09.
- Root cause: signed authorization and monotonic sequencing were specified
  without stale-command exclusion.
- Impact: an older authorized command can activate after a concurrent revoke or
  rotation and permit remote source disclosure.
- Smallest complete correction: require exact active-record CAS coordinates for
  every activate/rotate/revoke/rollback transition and define install-only,
  idempotent replay, and stale-command outcomes.
- Verification: race two valid transitions from one digest; exactly one wins,
  the loser is stale, duplicate replay is idempotent, and revoked/losing policy
  produces zero transport calls.

### DREV-008: Initial active deployment topology and writer ownership are unselected

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Finding type: architecture and external decision
- Affected scenario: approval of the ordinary production composition; product
  priority is not assigned because the design intentionally has no selected
  product behavior.
- Design evidence: SIA-R08, SIA-R16, SIA-R19 and lines 2137-2142 defer inference
  owner, writeback owner, local assets, packaging, supported host profiles, and
  resource values.
- Governing evidence: `docs/design/memorii_spec.md:1263-1279` assigns model
  invocation to the host and `docs/design/memorii_spec.md:1396-1404` makes the
  host decide persistence of writeback candidates, while the target design
  requires an active Memorii semantic-ingestion path.
- Impact: implementation must invent ownership and deployment semantics or
  remain evidence-only.
- Required external correction: the product/spec/deployment owner must choose
  the inference and persistence authority, exact approved local assets and
  licenses, supported host/resource profiles, capacity/deadline values, normal
  factory composition, remote policy, and rollback owner.
- Verification: owner stripping, default in-memory/filesystem constructors with
  networking denied, package/asset/profile consistency, unsupported profile,
  and explicit remote opt-in tests.

### DREV-009: Initial statistical and monitoring baseline values are absent

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Finding type: ML acceptance governance and external evidence
- Affected scenario: certification and activation; no product-incidence claim
  applies to an absent approval artifact.
- Design evidence: the design defines artifact shape and numeric invariants but
  explicitly leaves thresholds, alpha allocation, cluster minima, unsupported
  cells, and freshness deadlines to external approval around lines
  11015-11230.
- Violated requirements: SIA-R14, SIA-R15, hardening C4.
- Impact: an implementation cannot certify or activate a capability without
  inventing the acceptance policy.
- Required external correction: the product/ML acceptance owner must provide a
  signed, content-bound initial baseline artifact containing the complete gate
  and monitoring policy.
- Verification: independent metric, cluster, confidence-bound, multiplicity,
  freshness, substitution, stale, and rollback validation from immutable
  event-level evidence.

### DREV-010: The implementation assessment baseline is stale

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: traceability and implementation readiness
- Design evidence: lines 4-8 declare `f76850f` plus uncommitted changes; the
  reviewed repository baseline is `44cd7773a75ac8545ddcf799c76dc94c0240f788`.
- Violated requirement: SIA-R03 and the `$review-design` frozen-baseline rule.
- Root cause: the implementation changes were committed during the preceding
  review and the design header was not rebaselined.
- Impact: current-owner, migration, and test references are not reproducibly
  tied to the implementation being reviewed.
- Smallest complete correction: update the assessment baseline and revalidate
  all current-owner, public-contract, persistence, composition, and test
  references against `44cd7773…`.
- Verification: static reference audit bound to repository revision, design
  digest, and cited module/symbol/test paths.

## Requirements Coverage

| Requirement | Status | Findings |
| --- | --- | --- |
| SIA-R01 | partial | DREV-001, DREV-002 |
| SIA-R02 | covered | None |
| SIA-R03 | partial | DREV-010 |
| SIA-R04 | partial | DREV-001, DREV-003 |
| SIA-R05-SIA-R07 | covered | None |
| SIA-R08 | blocked | DREV-006, DREV-008 |
| SIA-R09 | partial | DREV-002, DREV-007 |
| SIA-R10 | contradictory | DREV-004 |
| SIA-R11-SIA-R12 | covered except primitive ownership | DREV-001 |
| SIA-R13 | partial | DREV-005 |
| SIA-R14-SIA-R15 | blocked | DREV-005, DREV-009 |
| SIA-R16 | blocked | DREV-005, DREV-006, DREV-008 |
| SIA-R17-SIA-R18 | covered | None |
| SIA-R19 | blocked | DREV-002, DREV-008 |
| SIA-R20-SIA-R21 | partial | DREV-003, DREV-006 |
| SIA-R22 | covered | None |
| SIA-R23 | partial | DREV-001-DREV-003 |

## Rejected, Consolidated, Or Reclassified Findings

- The historical request’s count is not used as evidence. The validated count
  happens to contain three P1 and four P2 findings under the current taxonomy.
- Missing implementation of the target modules is not a design defect; this is
  a proposed architecture. Only missing composition semantics are findings.
- The absent topology and absent statistical baseline are `Not applicable`, not
  P1/P2, because they are approval decisions without a selected product
  behavior or measured incidence.
- Existing tests not yet proving a future architecture are implementation work,
  not an additional design finding.
- No retrieval/query or agent-integration issue is admitted.

## Required Changes Before Approval

Determinate design revisions:

1. DREV-001: define and own foundational ingestion contracts.
2. DREV-002: define the trusted ingress resolver and production handoff.
3. DREV-003: compose one operation fence through every durable boundary.
4. DREV-005: lifecycle-bind baseline and resource-profile approvals.
5. DREV-006: define atomic local-admission reservations and recovery.
6. DREV-007: require CAS for every active egress transition.
7. DREV-010: rebaseline and revalidate implementation references.

External blockers:

1. DREV-004: event-model owner resolves equal-version replay semantics.
2. DREV-008: product/spec/deployment owner selects ownership and topology.
3. DREV-009: product/ML acceptance owner supplies the approved baseline.

## Final Outcome

**Blocked.** The design writer can resolve all determinate findings, after which
a fresh whole-design review is required. Approval cannot be granted until the
three external blockers are resolved; they must remain explicit rather than be
silently defaulted.

## Review Limitations

No live, paid, or GitHub workflow was run. Reviewers could not execute the test
suite in their isolated environment because the system interpreter is Python
3.9 while the project requires Python 3.11 or newer and the available Python
3.12 environment lacked `pytest`. Findings are supported by direct design,
governing-document, production-code, and test-source inspection.
