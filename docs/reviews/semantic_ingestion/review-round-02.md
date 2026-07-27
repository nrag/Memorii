# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-2026-07-26-restart-round-02`
- Review mode: `full`
- Review outcome: `Blocked`
- Design baseline SHA-256:
  `22fa2e5688d5cae027a843b29e7cd4a5fca2c90acb9e3e5a470a29ea4146818a`
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation
- Scope: complete ingestion design, not only revision 01

## Executive Assessment

Revision 01 closes the foundational primitive, ingress-resolver, local
reservation, egress CAS, and implementation-baseline gaps. The operation-fence
correction is incomplete in typed result contracts. The approval-lifecycle
correction violates the design's production/acceptance isolation invariant.
Revision-local DREV identifiers also collide with the external-decision names,
making the remaining blockers ambiguous.

Three expected external blockers remain: production topology and ownership,
equal-version replay semantics, and initial statistical/monitoring policy.

## Confirmed Findings

### DREV-R2-001: Operation fence is still absent from terminal typed results

- Product priority: `P1`
- Approval disposition: `changes_required`
- Finding type: contract composition, transaction integrity
- Affected scenario and prevalence evidence: every ordinary graph-bound or
  pre-graph terminal ingestion returns a `SourceIngestionResult`; this is a
  mainstream path.
- Evidence: lines 2307-2331 require every group result and source result to
  carry the byte-identical `OperationFenceBinding`. Lines 8274-8315 define
  `PreGraphSourceIngestionResult` and `GraphBoundSourceIngestionResult` without
  the binding. The `TransactionGroupExecutionResult` variants also omit it.
- Root cause: revision 01 updated requests and operation state but did not run a
  complete typed field-closure audit over every promised result variant.
- Impact: a terminal result cannot independently prove it belongs to the
  admitted operation/fence, and substitution can survive schema validation.
- Smallest complete correction: add the binding to both source-result variants
  and both transaction-group result variants; require exact equality with the
  admitted operation, group persistence, summaries, deltas, and replay records.
- Verification: static field-closure audit plus binding omission/substitution
  mutations across every result variant and lost-acknowledgement replay.

### DREV-R2-002: Acceptance authority leaks into production activation

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: security and architecture
- Evidence: SIA-R13 and the production/acceptance ownership table forbid
  production imports of acceptance schemas, keys, and trust policy. Lines
  2506-2517 instead require a production verifier to load
  `acceptance/registry_release.py` releases and trust snapshots.
- Root cause: the revision reused an acceptance-only implementation instead of
  defining a production-owned deployment authorization boundary.
- Impact: implementation must either violate package ownership or skip
  lifecycle verification.
- Smallest complete correction: define a production-owned, read-only
  `DeploymentAuthorizationVerifier` and serialized signed authorization
  artifact/trust-store contract. Acceptance may independently verify and
  publish authorized bytes, but production imports no acceptance or oracle
  module.
- Verification: bidirectional static import tests; valid authorization enables
  the named baseline/profile; wrong-purpose, revoked, expired, substituted, or
  rollback authorization produces evidence-only behavior and zero learned or
  graph effects.

### DREV-R2-003: Review findings and external decisions share conflicting IDs

- Product priority: `Not applicable`
- Approval disposition: `changes_required`
- Finding type: governance and traceability
- Evidence: DREV-001 and DREV-002 name external topology/replay decisions at
  lines 220-222 and 2141-2147, but lines 2585-2586 reuse them for completed
  primitive/resolver findings. Lines 2579-2581 reference DREV-004, DREV-008, and
  DREV-009 without a canonical external-decision register.
- Root cause: ephemeral review-finding identifiers became durable design
  decision identifiers.
- Impact: implementers cannot unambiguously identify the owner, artifact, or
  unblock condition for deployment, replay, and statistical policy.
- Smallest complete correction: replace durable `DREV-*` references with one
  canonical external-decision register using stable design IDs. Keep review
  finding IDs only in review reports and revision history.
- Verification: static traceability audit rejects undefined, duplicate, or
  conflicting decision IDs and verifies each decision's owner, artifact,
  affected requirements, fail-closed behavior, and unblock condition.

### DREV-R2-004: Default production ownership and topology remain unselected

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Finding type: external architecture decision
- Requirements: SIA-R08, SIA-R16, SIA-R19.
- Evidence: the design deliberately leaves the inference/writeback owner,
  authenticated-host integration, local assets, licenses, supported profiles,
  capacity/deadline values, ordinary factory composition, and rollback owner
  unresolved. Before selection, local promotion is `profile_unapproved`.
- Required decision: product/spec/deployment owner supplies one signed,
  content-addressed topology and ownership artifact.
- Verification after decision: owner stripping, authenticated host adapter,
  ordinary constructors with networking denied, package/asset/profile
  consistency, unsupported-profile, and explicit remote-opt-in tests.

### DREV-R2-005: Equal-version replay semantics remain unresolved

- Product priority: `P2`
- Approval disposition: `blocks_approval`
- Finding type: external event-model decision
- Affected scenario and prevalence evidence: divergent historical collisions
  are important replay/recovery cases but not the dominant ingest path.
- Evidence: `event_model.md:218-287` remains internally contradictory; the
  target correctly fails closed rather than inventing a winner.
- Required decision: event-model owner selects one genesis/checkpoint-consistent
  rule and updates the governing event model.
- Verification after decision: every permutation of exact duplicates,
  non-identical equal-version events, current-writer collisions, checkpoints,
  upcasts, and mixed-version history.

### DREV-R2-006: Initial statistical and monitoring policy remains absent

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Finding type: external ML acceptance decision
- Requirements: SIA-R14, SIA-R15.
- Evidence: the design deliberately does not choose thresholds, multiplicity
  allocation, cluster minima, freshness deadlines, unsupported cells, or
  substantive monitoring limits.
- Required decision: product/ML acceptance owner supplies one signed,
  content-bound initial policy artifact.
- Verification after decision: independent event-level recomputation of every
  metric, cluster, confidence bound, multiplicity adjustment, freshness rule,
  and activation/rollback transition.

## Round-01 Closure Audit

| Round-01 finding | Round-02 status |
| --- | --- |
| DREV-001 primitives | closed |
| DREV-002 ingress resolver | closed at target-design level; concrete host adapter is part of external topology |
| DREV-003 operation fence | partial; DREV-R2-001 |
| DREV-004 replay | external blocker; DREV-R2-005 |
| DREV-005 approval lifecycle | regressed isolation; DREV-R2-002 |
| DREV-006 local reservation | closed |
| DREV-007 egress CAS | closed |
| DREV-008 topology | external blocker; DREV-R2-004 |
| DREV-009 statistical policy | external blocker; DREV-R2-006 |
| DREV-010 implementation baseline | closed |

## Required Revision Before Final Review

The same sole design writer must make only these determinate corrections:

1. close operation-fence fields across every terminal result variant;
2. replace acceptance-module use with a production-owned deployment
   authorization verifier and artifact boundary;
3. create a stable external-decision register and remove ambiguous `DREV-*`
   references from normative design text.

The writer must not choose the three external decisions.

## Final Outcome

**Blocked.** One P1 determinate defect, two governance corrections, one P2
external blocker, and two `Not applicable` external blockers remain. One final
revision and fresh round-03 review are available within the budget.
