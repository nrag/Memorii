# Observed Provenance Materialization Design

- Work ID: observed-provenance-materialization
- Work type: design
- Status: blocked
- Coordinator: root
- Created: 2026-09-08
- Last updated: 2026-09-08
- Parent WorkPlan: ../engineering-closure/implementation.plan.md
- Related WorkPlans: ../observation-ledger/milestones/continuation-runtime.plan.md
- Canonical inputs: docs/design/semantic_ingestion_architecture.md; docs/design/semantic_ingestion_observation.md; proposal.md
- Expected outputs: reviewed exact read-only field recipes and bounded feasibility evidence

## Objective And Completion Contract

Resolve the confirmed underdefinition of proof ancestry and policy fingerprints
without inventing missing authority or weakening graph/overlay separation.
Complete only after typed feasibility, frozen candidate review by spec,
correctness and test reviewers, no unresolved required findings, canonical
promotion and affected authority/gate refresh. This is not runtime completion.

## Current State, Scope And Decisions

Spec consultation confirms paired citation target is determinate; proof and
policy tuple membership is not. Proposal defines exact retained context tuples.
Root owns draft/model/docs; no production implementation of these new semantics
is authorized yet. Existing public/host wiring is unverified work in progress.
No user keys/measurements are needed for this engineering contract choice.
All native operation arms share the same tuple recipe; legacy missing authority
fails closed. No public schema field or persisted record changes are included.

## Evidence, Attack And Cost Ledger

Requirements: exact paired target; complete typed ancestry; complete declared
policy context; original bytes/history; one detached inventory; bounded denial.
Proof: typed model field construction, exact output tuples and targeted missing,
substitution, ambiguity, duplicate/order and optional-bundle mutations. External
provider quality, production signatures and operational evidence excluded.
Delegation: prior spec consultation read-only; root drafts; three reviewers will
inspect one frozen candidate after proof. Budget: one full and two delta rounds.

## Identity, Changed Surface And Authority Chain

Only proposal.md, design.plan.md and a feasibility model/test are owned here.
All identifiers describe behavior; requirement IDs are documentation traceability.
Normative promotion -> canonical hash consumers -> registry/source authority and
workflow pins -> prescribed deterministic gates. No false unchanged-pin claim.
Graph schemas/roles remain unchanged unless review demonstrates a required delta.

## Next Action

Obtain the design-owner choice of declared context versus applied-only policies, then complete the corresponding typed feasibility matrix.

## Rejected Recipe Candidate

Native fact feasibility passed1 test in53.60s; evidence/native-fact.log retained.
candidate.json pins the original proposal/model/tests and governing/native source
bytes; those exact inputs are preserved under history/. The current proposal
contains review corrections and is not the frozen reviewed candidate.
This proves existing fact-route fields can supply the proposed tuples, not all
operation-arm runtime behavior or public endpoint correctness. Root owns the
draft; public wiring is preserved as an inactive patch.

## Review Reconciliation

All three bounded reviews require changes. Confirmed conformance/evidence
actions: include optional identity policy; include outer correction plus nested
fact effect digests; prove exact paired native provenance/citation/target joins;
extend typed non-runtime family proof beyond fact. Duplicate findings are merged
under these four causes. No product severity is inferred from missing evidence.
No candidate approval, canonical promotion or implementation of these new
semantics is authorized. One full review consumed; two delta rounds remain.

The exposed policy list's meaning is a public semantic choice: the proposal
selects declared retained context, including policies not necessarily consulted
for a particular field. Existing documents do not select declared versus applied
context. Obtain explicit design-owner acceptance after the proposal is complete
and reviewed; do not infer it from missing production signing keys.

## Exact Decision Blocker

User question is pending via the conversation: complete retained policy context
or only proven-applied policies. The recommended proposal is reviewable and
includes the confirmed identity/correction corrections. Applied-only requires
new persisted execution tracing, changing the implementation and proof scope.
Keep the current draft noncanonical until the owner selects this meaning.
Public composition edits are preserved in public-composition-draft.patch, not
active production code; the referenced materializer does not yet exist.
Independent registered access and ingestion-record conversion remain verifiable
under their existing approved contracts.
