# Design Review: Semantic Ingestion Internal Closure

## Review Metadata

- Review ID: `semantic-ingestion-internal-closure-round-01`
- Review mode: `full`
- Review outcome: `Changes required; external decisions remain blocked`
- Design baseline SHA-256:
  `c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e`
- Design size: 13,046 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation and reconciliation with
  prior unresolved findings

## Executive Assessment

The initial independent pass reproduced the user's expected one P1 and one P2:
durable delivery identity is incorrectly coupled to expiring authentication,
and governed snapshots can semantically re-ingest messages already admitted as
turns. After the independent pass, all reviewers re-evaluated the prior
unresolved report against the unchanged baseline. They unanimously confirmed
the execution-DAG contradiction, lost per-message governance carrier, and
incomplete detailed-clause traceability.

The frozen internal inventory is therefore two P1 findings, two P2 findings,
and one `Not applicable` design-governance finding with
`changes_required` disposition. The user's one-P1/one-P2 count was an estimate,
not a complete inventory. No finding has been added merely because the proposed
architecture is not implemented.

The three registered external decisions remain separate and unchanged.

## Confirmed Internal Findings

### SIC-001: Durable delivery identity depends on an expiring authorization session

- Product priority: `P1`
- Approval disposition: `changes_required`
- Finding type: idempotency, recovery, and authorization boundary
- Requirements: SIA-R01, SIA-R23, and hardening C11
- Evidence: the delivery namespace and key bind
  `AuthenticatedIngressContext.context_digest` at lines 2317-2350; that digest
  includes session identity, policy/trust revision, issue time, and expiry at
  lines 2383-2394. Recovery requires the same authenticated context and delivery
  key at lines 2444-2450 and 3783-3798.
- Violated invariant: durable idempotency identity must survive ordinary
  credential renewal while current authorization is independently rechecked.
- Failure scenario: admission commits and its acknowledgement is lost. A retry
  after session refresh or ingress-policy rotation derives a different delivery
  key, cannot recover the first operation, and can create a second source and
  graph effect. Reusing the expired context instead fails authorization.
- Prevalence: short-lived credentials, reconnects, and at-least-once retries are
  ordinary production behavior, so the default recovery path is affected.
- Root cause: volatile authorization evidence is used as durable delivery
  identity rather than as a separately validated admission/recovery proof.
- Smallest complete correction: define a stable, server-derived
  `DeliveryPrincipalBinding` from immutable provider, principal, tenant, and
  authorized delivery-scope coordinates. Derive durable delivery identity from
  that binding and the normalized public delivery ID. Persist session-bound
  authorization evidence separately, and reauthorize the stable binding on
  retries and result access.
- Independent verification: two-process retries across session renewal and
  policy/trust rotation recover byte-identical admission/result with one graph
  effect; revoked, cross-principal, cross-tenant, and out-of-scope retries are
  non-disclosing and mutation-free.

### SIC-002: Normative execution DAG contradicts the closed stage registry

- Product priority: `P1`
- Approval disposition: `changes_required`
- Finding type: typed execution contract and observability
- Requirements: SIA-R03 and SIA-R04
- Evidence: the closed `IngestionStage` union at lines 7533-7569 distinguishes
  `source_proposal_alignment`, `capability_selection`,
  `planned_identity_reservation`, `graph_proposal_alignment`, and
  `capability_status_binding_validation`. Lines 8318-8352 forbid a generic
  `proposal_alignment` alias and reject missing/collapsed stages. The normative
  rendering at lines 11914-11945 uses the forbidden alias and omits mandatory
  stages.
- Violated invariant: execution, persistence, retry, and certification must use
  one typed, fingerprinted graph with the same stages, scopes, and edges.
- Failure scenario: every promoted source reaches alignment, but a conforming
  trace producer cannot represent the displayed graph. Implementers must invent
  aliases or silently omit required source-plan and graph-attempt stages.
- Prevalence: the contradiction affects every ordinarily promoted source.
- Root cause: the observability rendering was manually maintained separately
  from the closed stage registry.
- Smallest complete correction: make one typed execution-graph template
  authoritative and mechanically derive the rendered DAG from it. Include every
  registered mandatory stage, scope, and dependency and remove every alias.
- Independent verification: static exact equality across registry, canonical
  template, rendered graph, and emitted manifests, including blocked and
  `not_started` instances.

### SIC-003: Governed message semantics are not carried through downstream contracts

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: security and semantic carrier closure
- Requirements: SIA-R01, SIA-R04, SIA-R09, SIA-R22, and SIA-R23
- Evidence: `GovernedMessageSemanticContext` at lines 2352-2360 defines
  per-message scope, authority, classification, modality, and egress
  eligibility; projection segments reference its digest at lines 3635-3647 and
  3754-3759. `PreparedSource`, `SemanticProposalRequest`,
  `ReconciliationRequest`, and `GraphCompilationRequest` instead retain only
  source-wide context or egress coordinates at lines 3958-3969, 4119-4133,
  5448-5468, and 6167-6187.
- Violated invariant: exact authenticated message governance must survive
  proposal, reconciliation, compilation, persistence, replay, and result access
  without source-wide reconstruction.
- Failure scenario: one governed snapshot contains messages with different
  scopes, classifications, authorities, or egress eligibility. A denied segment
  may use a source-level allow decision or compile under the wrong scope.
- Prevalence: governed multi-message snapshots are an important supported
  lifecycle path, while ordinary single-turn ingestion remains unaffected.
- Root cause: message governance ends at projection and lacks a typed immutable
  downstream carrier.
- Smallest complete correction: add one immutable segment-governance binding
  keyed by `message_semantic_context_digest`, including the exact egress
  decision, and carry it through every request, attempt, accepted operation,
  transaction group, compiler input, durable/replay artifact, and terminal
  result. Reject unsupported cross-context operations.
- Independent verification: mixed-scope/classification/authority/egress
  snapshots prove byte-identical carrier closure, zero calls for denied
  segments, no wrong-scope mutation, replay preservation, and non-disclosing
  result access.

### SIC-004: Turn and snapshot routes can semantically ingest the same message twice

- Product priority: `P2`
- Approval disposition: `changes_required`
- Finding type: source lifecycle and cross-entry-point idempotency
- Requirements: SIA-R01 and SIA-R23
- Evidence: governed snapshot message IDs are unique only within one envelope at
  lines 3550-3591. The mapping at lines 3619-3626 admits turns and governed
  snapshots as separate source kinds, while lines 3738-3759 project every
  governed snapshot message. No shared durable message identity or atomic reuse
  rule spans turn, `pre_compress`, and `session_end` routes.
- Violated invariant: replay or representation of one authenticated host
  message through another lifecycle hook must not create duplicate semantic
  effects.
- Failure scenario: a turn is admitted and later appears in a governed snapshot.
  The snapshot has a different source/delivery identity and promotes the same
  message again, duplicating claims, actions, or provenance.
- Prevalence: this is important once governed compaction and session snapshots
  are enabled; metadata-poor snapshots remain evidence-only.
- Root cause: envelope-local `message_id` is not a durable canonical
  message-admission identity shared by all provider entry points.
- Smallest complete correction: add a server-derived, scope-bound
  `MessageAdmissionIdentity` from authenticated source reference and immutable
  message bytes. Resolve turns and snapshots through one atomic index: exact
  repeats reuse the prior admission/result, changed bytes reject, and snapshots
  schedule only unseen messages while retaining the complete snapshot as
  evidence. Define legacy cutover explicitly.
- Independent verification: cross-process turn-to-snapshot and overlapping
  snapshot tests prove one admission/effect set per message, fresh-only
  scheduling, exact replay, changed-byte rejection, and deterministic cutover.

### SIC-005: Detailed normative clauses lack authoritative reverse traceability

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: design governance and verification completeness
- Requirement: SIA-R03
- Evidence: SIA-R03 at line 215 requires every material requirement to have a
  stable source, owner, acceptance rule, and verification path. The ledger and
  architecture-acceptance audit at lines 202-299 and 12781-12786 cover broad SIA
  rows and historical CFP/ING rationale labels, but material normative clauses
  in Sections 3-5 have no complete stable clause-to-owner/test/evidence index.
- Violated invariant: no material normative clause may be silently omitted by
  implementation or verification while its broad parent requirement is marked
  complete.
- Failure scenario: an implementation omits a required atomicity, security,
  installed-artifact isolation, migration, or recovery clause while the broad
  SIA row and existing traceability audit remain green.
- Root cause: detailed executable requirements expanded without a closed reverse
  traceability contract.
- Smallest complete correction: assign stable invariant IDs to every material
  normative clause and define an authoritative machine-checkable ledger mapping
  each ID to its SIA parent, owner, measurable assertion, named test group, and
  evidence artifact. Reject missing, stale, or orphaned entries.
- Independent verification: mutation tests remove or add each mapping, owner,
  test, and evidence coordinate and prove the audit fails before implementation
  completion can be claimed.

## External Blockers

The following are unchanged, excluded from internal revision, and retain
`Not applicable` product priority with `blocks_approval` disposition:

* `SIA-ED-TOPOLOGY-001`: signed topology, ownership, resource-profile, and
  ordinary-composition authorization.
* `SIA-ED-REPLAY-001`: one governing genesis/checkpoint-consistent
  equal-version replay algebra and matching event-model update.
* `SIA-ED-POLICY-001`: signed initial statistical and monitoring policy with
  independently recomputed evidence.

## Rejected Or Reclassified Findings

* Missing production implementation of the proposed architecture is not a
  design defect. Implementation conformance remains a later gate.
* Current benchmark tests using retrieval or alias fallback cannot certify the
  target, but the design already replaces them with a direct authorized
  structural observation boundary and independent source-introduction oracle.
* The prior P2 classification for detailed-clause traceability is reclassified
  to `Not applicable`: it is a design-governance defect without a demonstrated
  product-prevalence claim. Its `changes_required` disposition is unchanged.
* No query/retrieval or agent-integration finding is admitted.

## Round Outcome

**Changes required.** The revision scope is frozen to SIC-001 through SIC-005.
One design writer may make the smallest complete corrections. The three
registered external decisions must remain explicit and unresolved. After the
revision, the coordinator must freeze a new exact baseline and launch three new
whole-design reviewers.
