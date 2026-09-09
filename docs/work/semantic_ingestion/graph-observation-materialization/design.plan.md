# Complete Native Graph Observation Materialization

- Work ID: graph-observation-materialization
- Work type: design
- Status: blocked
- Coordinator: root
- Created: 2026-09-08
- Last updated: 2026-09-08
- Parent WorkPlan: ../engineering-closure/implementation.plan.md
- Related WorkPlans: ../observed-provenance-materialization/design.plan.md
- Canonical inputs: docs/design/semantic_ingestion_observation.md; docs/design/semantic_ingestion_architecture.md; root AGENTS.md and its governing source order
- Expected outputs: one closed field/identity recipe, feasibility proof, independent design reviews, then a separate implementation continuation

## Objective And Scope

Make the complete public graph observation materializer implementable without
inventing missing structural fields or a projection identity hash. Preserve the
approved complete retained provenance/policy context. This operation does not
reopen that decision, provision production keys, issue acceptance witnesses, or
claim semantic ingestion closure.

## Baseline And Current State

Baseline 7a92bce208ecfb7d8ff199e629edb09f663d1948. Public composition was briefly
applied during construction, then parked again after actual field mapping found
unresolved semantics. The four files in drafts/ are incomplete, unverified
construction artifacts, deliberately outside the production import tree. They
must not be copied into production without replacing their incomplete paths.
The earlier public composition patch remains under the related provenance plan.

The independent correctness consultation confirmed that observation_id has no
registered preimage/constructor: ObservedTemporalClaimProjection and
ObservedTrustClaimProjection accept a nonempty string; their registered
record_digest commits that string rather than derives it. Native projection
digests do not bind the required generation and observation profile.

Root confirmed that EntityRevision lacks canonical_type/valid_interval and
RelationRevision lacks lifecycle/valid_interval. Native facts, construction
authority, event batches and evidence projections contain substantial related
data, but choosing one of those meanings requires an explicit rule. This is a
design-readiness miss; it is not missing user signing material.

## Finding Disposition And Sources

Confirmed: Not applicable / blocks_approval / architecture, missing registered
projection identity recipe (observation addendum lines1235,1650; observed models
and digest-signature roles). Confirmed: Not applicable / changes_required /
design completeness, missing native structural field derivation rules.

Rejected delegate claims: LineageEvidenceReference does have source_id
(semantic_state.py:194); ClaimAssertion does retain claim_identity and temporal
evidence (contracts.py:1479); native operation/effect joins are available through
group request transaction_group_id and ordered_operation_inputs.operation_id;
reference paths and boundary membership are already governed by the generated
reference manifest and changed/boundary record keys. These are implementation
work, not reasons to request new user decisions.

## Proposed Decision

See proposal.md. It presents one recommended complete structural meaning and
one alternative. It is not a promoted normative amendment or an approved design.
External decision: accept the proposed read-only field semantics and registered
projection identity before implementing public output with those meanings.
Remaining engineering questions (source-span exact joins, same-time version
visibility and complete arm coverage) must be settled by feasibility/review;
owner agreement alone will not establish implementation readiness.

## Constraints, Compatibility And Authority Chain

No graph/event/provenance history may be rewritten. Public observation remains
authenticated, scoped, detached, bounded, complete and fail closed. No adapter
arbitrates belief or trust. Proposed new identity names are behavioral protocol
identities, never milestone/requirement coordinates.

If approved: proposal -> canonical addendum -> explicit identity model and
authored registry roles -> decoder/source inventory -> compiled publication ->
independent vectors/checksums/workflow pins -> reader/materializer -> public
provider proof. No executable or registry changes are made by this proposal.
Rollout must retain historical publication readers; rollback disables new
observation publication, never bypasses the ledger or mutates history.

## Verification And Completion Contract

Before promotion, prove exact native field availability with retained built-in
fact, correction, retraction, action and identity artifacts or disclose the
unavailable production arm. Verify missing/duplicate/cross-operation evidence,
same-time version handling, scope/boundary closure, separate history selection,
swapped kind/repository/generation/projection identity, and independent registered
identity reconstruction. Run spec/correctness/test reviews on one frozen complete
candidate. Record remaining_validated_p1_p2: [] only after reconciliation.

An approval of this proposal cannot close R17/R19. Later implementation must
prove real ProviderMemoryService calls, full streams, continuation, corruption,
restart and resource limits. Deterministic, CI and operational evidence remain
separate. No current CI or full design approval is claimed.

## Delegation And Evidence

Spark maps were advisory; root corrected unsupported field/lock claims.
Terra materializer workers stopped on confirmed field ambiguities; their partial
drafts are preserved outside production. Terra correctness consultation verified
the projection identity gap. No full reviewer cohort was launched on incomplete
drafts. Root owns this proposal and all evidence/decisions.

## Next Action

Obtain the owner decision on proposal.md, then complete the bounded field and
identity feasibility/review before resuming public materialization.
