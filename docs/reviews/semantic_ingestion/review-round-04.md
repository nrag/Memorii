# Design Review: Source-Grounded Semantic Ingestion Architecture

## Review Metadata

- Review ID: `semantic-ingestion-2026-07-26-restart-round-04`
- Review mode: `full`
- Review outcome: `Changes required; revision budget exhausted`
- Design baseline SHA-256:
  `c80a83e3281e020cdcaf971f5ef3c95fa36ed96a26542b90f882dee7e7ed833e`
- Design size: 13,046 lines
- Implementation baseline:
  `44cd7773a75ac8545ddcf799c76dc94c0240f788`
- Reviewers: fresh independent `spec_auditor`, `correctness_reviewer`, and
  `test_reviewer`, followed by coordinator validation

## Executive Assessment

Revision 03 closes authenticated semantic-result lookup and independent
baseline-approval evidence. The fresh whole-design review nevertheless found
three internal gaps that prevent approval: the normative execution DAG
contradicts its closed stage registry, governed message semantics are not
carried through downstream contracts, and detailed normative clauses are not
covered by an authoritative reverse traceability audit.

The coordinator rejected findings whose only evidence is that the proposed
architecture and target tests have not yet been implemented. Implementation
absence is expected before an implementation WorkPlan and is not an internal
design defect where the design already specifies the required production
boundary and independent oracle.

Three registered external decisions also remain unresolved. Because all three
permitted design revisions have been used, this report closes the workflow as
not converged. The canonical design is not approved and is not
implementation-ready.

## Confirmed Internal Findings

### DREV-R4-001: Normative execution DAG contradicts the closed stage registry

- Product priority: `P1`
- Approval disposition: `changes_required`
- Requirements: SIA-R03 and SIA-R04
- Evidence: the `IngestionStage` union at lines 7533-7569 contains distinct
  `source_proposal_alignment` and `graph_proposal_alignment` literals. Lines
  8318-8352 prohibit a generic `proposal_alignment` alias and require every
  registered stage at its declared scope. The normative rendering at lines
  11914-11945 nevertheless uses `proposal_alignment` and omits mandatory
  stages including `capability_selection`, `planned_identity_reservation`,
  `graph_proposal_alignment`, and
  `capability_status_binding_validation`.
- Violated invariant: one fingerprinted, typed execution graph must define the
  exact stage set, scopes, and dependencies used by execution, persistence,
  retry, and certification.
- Failure scenario: every ordinarily promoted source reaches alignment, but an
  implementation cannot emit the rendered DAG through the closed type. It must
  accept a forbidden alias, omit required stages, or invent stage mappings and
  edges. Trace persistence, causal blocking, retry replay, and certification
  can therefore disagree about work that occurred.
- Root cause: the compact observability rendering was maintained independently
  from the closed execution-graph contract.
- Exact architectural change required: define one authoritative typed
  execution-graph template; mechanically derive the Section 5.8 rendering from
  it; include every mandatory stage with its permitted scope and exact
  dependencies; reject aliases and missing stages.
- Completion evidence: a static exact equality check proves the canonical
  template, closed registry, rendered DAG, and emitted trace manifests have the
  same stage instances, scopes, and edges, including blocked/not-started
  instances.

### DREV-R4-002: Governed message semantics are lost after source admission

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirements: SIA-R01, SIA-R04, SIA-R09, SIA-R22, and SIA-R23
- Evidence: lines 2352-2360 permit per-message scope, authority,
  classification, modality, and egress eligibility; lines 2369-2374 and
  3754-3759 require each conversation segment to reference its exact message
  context. Downstream contracts instead retain a source-wide
  `SourceSemanticContext`: `PreparedSource` at lines 3958-3969,
  `ReconciliationRequest` at lines 5448-5468, and
  `GraphCompilationRequest` at lines 6167-6187. `SemanticProposalRequest` at
  lines 4119-4133 carries a source-bound egress-decision digest but no immutable
  message-governance binding, although transport at lines 2478-2483 must
  revalidate the segment context.
- Violated invariant: exact authenticated message scope, authority,
  classification, and egress semantics must survive promotion, persistence,
  replay, and result disclosure without source-wide inference.
- Failure scenario: a governed snapshot contains messages with different
  scopes or egress eligibility. A proposal or accepted operation can be
  compiled under the wrong source-wide scope, or a source-level allow decision
  can authorize transport of a denied segment.
- Root cause: the design defines message governance at projection time but no
  typed, immutable carrier closure through proposal, reconciliation,
  compilation, persistence, replay, and terminal results.
- Exact architectural change required: introduce one immutable
  segment-governance binding keyed by
  `message_semantic_context_digest`, including the bound egress decision, and
  carry it through every downstream request, attempt, accepted operation,
  transaction group, compiler input, event/replay artifact, and terminal
  result. Reject cross-context semantic operations unless a separately
  specified and certified multi-context operation exists.
- Completion evidence: positive single-context tests and adversarial
  mixed-scope, mixed-authority, mixed-classification, and mixed-egress snapshot
  tests prove exact carrier equality, no wrong-scope graph mutation, zero wire
  activity for denied segments, replay preservation, and non-disclosing result
  access.

### DREV-R4-003: Detailed normative clauses lack complete reverse traceability

- Product priority: `P2`
- Approval disposition: `changes_required`
- Requirement: SIA-R03
- Evidence: SIA-R03 at line 215 requires every material requirement to have a
  source, owner, acceptance rule, and verification path. The ledger covers the
  broad SIA-R01-SIA-R23 rows, and lines 260-299 map historical rationale labels,
  but material normative clauses in Sections 3-5 do not have stable clause IDs
  and an authoritative reverse mapping. The acceptance rule at lines
  12781-12786 audits only SIA rows and rationale labels.
- Violated invariant: no material normative clause may be silently omitted by
  implementation, verification, or evidence collection.
- Failure scenario: an implementation omits a mandatory atomicity,
  installed-artifact isolation, security, migration, or recovery clause while
  marking its broad SIA parent complete; the stated traceability audit still
  passes.
- Root cause: detailed executable requirements expanded without a closed
  clause-to-requirement/test/evidence index.
- Exact architectural change required: assign stable invariant IDs to every
  material normative clause in Sections 3-5 and maintain an authoritative
  reverse ledger to its SIA requirement, owner, measurable assertion, named
  test group, and evidence artifact. The audit must fail for an unmapped clause,
  stale owner, missing test/evidence group, or orphaned test group.
- Completion evidence: mutation tests independently remove each mapping,
  owner, test group, and evidence coordinate and prove the audit fails; adding
  an unindexed normative clause must fail before implementation completion can
  be claimed.

## External Blockers

### SIA-ED-TOPOLOGY-001

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Required action: the product/spec/deployment owner publishes the signed,
  content-addressed topology and resource-profile authorization named in the
  external-decision register. Its exact bytes must pass production deployment
  authorization, bidirectional package/asset/profile validation, ordinary
  constructor no-network verification, unsupported-host behavior, and rollback
  verification.

### SIA-ED-REPLAY-001

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Required action: the event-model owner updates
  `docs/design/event_model.md` and publishes the governing signed artifact that
  selects one genesis/checkpoint-consistent algebra for exact duplicates,
  non-identical historical equal-version events, and current-writer collisions.
  Arrival-order, checkpoint, upcast, and mixed-version permutations must pass.

### SIA-ED-POLICY-001

- Product priority: `Not applicable`
- Approval disposition: `blocks_approval`
- Required action: the product/ML acceptance owner publishes the signed,
  content-bound initial statistical and monitoring policy with every threshold,
  multiplicity allocation, cluster minimum, unsupported cell, freshness
  deadline, and monitoring limit. Independent event-level recomputation must
  validate the complete artifact for the exact capability/dependency bundle.

## Rejected Findings

- The current production implementation does not yet implement the proposed
  architecture. This is an implementation-planning concern, not a defect in a
  proposed design that already makes implementation and conformance tests an
  explicit future gate.
- The current benchmark oracle uses alias/type fallback. It cannot serve as
  target acceptance evidence, but the design already retires that behavior in
  favor of the authorized structural observation API and a unique
  source-introduction bijection. No additional design correction is required.
- The stale active WorkPlan baseline was a P3 review-record defect. It is
  corrected by this report and the linked WorkPlan updates, not by changing the
  architecture.
- No retrieval/query or agent-integration finding is admitted.

## Final Outcome

**Changes required; revision budget exhausted.** The workflow ends with one P1
and two P2 internal design findings plus three registered external blockers.
Approval requires a new user-authorized design-revision operation that closes
DREV-R4-001 through DREV-R4-003, followed by a fresh whole-design review of the
new exact baseline. External approval additionally requires resolution of
SIA-ED-TOPOLOGY-001, SIA-ED-REPLAY-001, and SIA-ED-POLICY-001. No further edits
are permitted under this WorkPlan.
